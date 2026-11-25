import 'dart:convert';
import 'dart:io' show Platform;

import 'package:android_id/android_id.dart';
import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

class PunchDevice {
  static const _storage = FlutterSecureStorage();
  static const _key = 'klockin.device-id';

  Future<String>? _activeRead;

  bool get supportsBinding => !kIsWeb && (Platform.isAndroid || Platform.isIOS);

  Future<String> read() async {
    final active = _activeRead;
    if (active != null) return active;
    final lookup = _read();
    _activeRead = lookup;
    try {
      return await lookup;
    } finally {
      _activeRead = null;
    }
  }

  Future<String> _read() async {
    final existing = await _storage.read(key: _key);
    if (existing != null && existing.isNotEmpty) return existing;

    final String? identifier;
    if (!kIsWeb && Platform.isAndroid) {
      identifier = await const AndroidId().getId();
    } else if (!kIsWeb && Platform.isIOS) {
      identifier = (await DeviceInfoPlugin().iosInfo).identifierForVendor;
    } else {
      identifier = null;
    }

    final id = identifier == null || identifier.isEmpty
        ? const Uuid().v4()
        : sha256.convert(utf8.encode('klockin:$identifier')).toString();
    await _storage.write(key: _key, value: id);
    return id;
  }
}

final punchDeviceProvider = Provider<PunchDevice>((ref) => PunchDevice());
