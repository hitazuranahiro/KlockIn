import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/auth/session_lock.dart';

typedef PunchEvidence = ({double latitude, double longitude, Uint8List selfie});

/// Pending punch evidence is authenticated and encrypted before SQLite sees it.
class PunchEvidenceCipher {
  PunchEvidenceCipher(this._loadKey);

  factory PunchEvidenceCipher.device(SessionLock lock) {
    const storage = FlutterSecureStorage(
      iOptions: IOSOptions(
        accessibility: KeychainAccessibility.first_unlock_this_device,
      ),
    );
    const slot = 'klockin.punch-evidence-key.v1';
    return PunchEvidenceCipher(
      () => lock.run(() async {
        final current = await storage.read(key: slot);
        if (current != null) {
          final bytes = base64Decode(current);
          if (bytes.length != 32)
            throw const FormatException('Invalid evidence key');
          return SecretKey(bytes);
        }
        final key = await AesGcm.with256bits().newSecretKey();
        await storage.write(
          key: slot,
          value: base64Encode(await key.extractBytes()),
        );
        return key;
      }),
    );
  }

  static const _nonceLength = 12;
  static const _macLength = 16;
  static const _coordinateBytes = 16;
  static final _algorithm = AesGcm.with256bits();

  final Future<SecretKey> Function() _loadKey;
  SecretKey? _key;

  Future<SecretKey> _getKey() async => _key ??= await _loadKey();

  List<int> _context(String purpose, String account, String uuid) =>
      utf8.encode('klockin/$purpose/v1\n$account\n$uuid');

  Future<Uint8List> seal(
    String account,
    String uuid,
    PunchEvidence evidence,
  ) async {
    final data = Uint8List(_coordinateBytes + evidence.selfie.length);
    ByteData.sublistView(data)
      ..setFloat64(0, evidence.latitude)
      ..setFloat64(8, evidence.longitude);
    data.setAll(_coordinateBytes, evidence.selfie);
    return _seal(_context('punch-evidence', account, uuid), data);
  }

  Future<PunchEvidence> open(
    String account,
    String uuid,
    Uint8List sealed,
  ) async {
    final clear = await _open(
      _context('punch-evidence', account, uuid),
      sealed,
    );
    if (clear.length <= _coordinateBytes) {
      throw const FormatException('Incomplete punch evidence');
    }
    final coordinates = ByteData.sublistView(clear);
    return (
      latitude: coordinates.getFloat64(0),
      longitude: coordinates.getFloat64(8),
      selfie: Uint8List.sublistView(clear, _coordinateBytes),
    );
  }

  Future<Uint8List> sealAddress(String account, String uuid, String address) =>
      _seal(_context('punch-address', account, uuid), utf8.encode(address));

  Future<String> openAddress(
    String account,
    String uuid,
    Uint8List sealed,
  ) async => utf8.decode(
    await _open(_context('punch-address', account, uuid), sealed),
  );

  Future<Uint8List> _seal(List<int> context, List<int> clear) async {
    final box = await _algorithm.encrypt(
      clear,
      secretKey: await _getKey(),
      aad: context,
    );
    return box.concatenation();
  }

  Future<Uint8List> _open(List<int> context, Uint8List sealed) async {
    final box = SecretBox.fromConcatenation(
      sealed,
      nonceLength: _nonceLength,
      macLength: _macLength,
    );
    return Uint8List.fromList(
      await _algorithm.decrypt(box, secretKey: await _getKey(), aad: context),
    );
  }
}
