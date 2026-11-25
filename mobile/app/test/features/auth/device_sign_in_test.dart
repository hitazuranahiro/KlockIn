import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/api_client.dart';
import 'package:klockin/core/api/api_failure.dart';
import 'package:klockin/core/auth/profile_store.dart';
import 'package:klockin/core/auth/session.dart';
import 'package:klockin/core/auth/session_lock.dart';
import 'package:klockin/core/auth/token_store.dart';
import 'package:klockin/features/auth/data/auth_api.dart';
import 'package:klockin/features/punch/data/location_service.dart';
import 'package:klockin/features/punch/data/punch_controller.dart';
import 'package:klockin/features/punch/data/punch_device.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';
import 'package:klockin/features/punch/data/punch_sync.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../support/punch_evidence.dart';

const _host = 'https://time.example';
const _deviceId = 'test-installation-id';

class _Device extends PunchDevice {
  int reads = 0;

  @override
  bool get supportsBinding => true;

  @override
  Future<String> read() async {
    reads++;
    return _deviceId;
  }
}

class _Tokens implements TokenStore {
  StoredSession? session;

  @override
  Future<StoredSession?> read() async => session;

  @override
  Future<void> write(StoredSession session) async {
    this.session = session;
  }

  @override
  Future<void> clear() async {
    session = null;
  }
}

class _Profiles implements ProfileStore {
  StoredProfile? profile;

  @override
  Future<StoredProfile?> read() async => profile;

  @override
  Future<void> write(StoredProfile profile) async {
    this.profile = profile;
  }

  @override
  Future<void> clear() async {
    profile = null;
  }
}

class _PunchRecorder extends PunchSync {
  _PunchRecorder(Ref ref) : super(ref);

  QueuedPunch? punch;

  @override
  Future<PunchReceipt> record(Session session, QueuedPunch punch) async {
    this.punch = punch;
    return const PunchReceipt(PunchSyncState.pending);
  }
}

class _LoginServer implements HttpClientAdapter {
  _LoginServer({this.base = _host});

  final String base;
  Map<String, dynamic>? loginBody;
  bool differentDevice = false;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (options.uri.toString() == '$base/health/') {
      return _response(200, {
        'status': 'ok',
        'product': 'klockin',
        'mobile_api_contract': 2,
      });
    }
    expect(options.uri.toString(), '$base/api/v1/auth/login/');
    loginBody =
        jsonDecode(await utf8.decoder.bind(requestStream!).join())
            as Map<String, dynamic>;
    return differentDevice
        ? _response(403, {
            'code': 'device_mismatch',
            'detail': 'This account is already linked to another device.',
          })
        : _response(200, {
            'access': 'test-access',
            'refresh': 'test-refresh',
            'employee': {'id': 4, 'full_name': 'Employee'},
            'capabilities': {
              'permissions': {'attendance': true},
            },
          });
  }

  ResponseBody _response(int status, Map<String, dynamic> body) =>
      ResponseBody.fromString(
        jsonEncode(body),
        status,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
}

void main() {
  test('mobile sign-in and the first punch send the same device ID', () async {
    sqfliteFfiInit();
    final db = await SqlitePunchQueue.open(
      databaseFactoryFfi,
      inMemoryDatabasePath,
      testPunchCipher,
    );
    addTearDown(db.close);
    final server = _LoginServer();
    final device = _Device();
    final tokens = _Tokens();
    late _PunchRecorder recorder;
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(
          ApiClient(
            tokenStore: tokens,
            onSessionLost: () {},
            dio: Dio()..httpClientAdapter = server,
          ),
        ),
        tokenStoreProvider.overrideWithValue(tokens),
        sessionLockProvider.overrideWithValue(MemorySessionLock()),
        profileStoreProvider.overrideWithValue(_Profiles()),
        punchDeviceProvider.overrideWithValue(device),
        punchQueueProvider.overrideWithValue(
          SqlitePunchQueue(Future.value(db), testPunchCipher),
        ),
        punchSyncProvider.overrideWith((ref) => recorder = _PunchRecorder(ref)),
      ],
    );
    addTearDown(container.dispose);

    await container
        .read(sessionProvider.notifier)
        .signIn(
          rawHost: _host,
          username: 'employee',
          password: 'test-password',
        );
    expect(server.loginBody?['device_id'], _deviceId);
    expect(tokens.session?.employeeId, 4);

    await container
        .read(punchControllerProvider)
        .submit(
          const PunchPreparation(
            isClockingIn: true,
            coordinates: Coordinates(latitude: 14.5, longitude: 121),
          ),
          Uint8List(1),
        );
    expect(recorder.punch?.deviceId, _deviceId);
    expect(device.reads, 2);
  });

  test('legacy login can omit the ID and mismatch has its own error', () async {
    final server = _LoginServer();
    final api = AuthApi(
      ApiClient(
        tokenStore: _Tokens(),
        onSessionLost: () {},
        dio: Dio()..httpClientAdapter = server,
      ),
    );

    await api.signIn(
      host: _host,
      username: 'employee',
      password: 'test-password',
    );
    expect(server.loginBody!.containsKey('device_id'), isFalse);

    server.differentDevice = true;
    await expectLater(
      api.signIn(
        host: _host,
        username: 'employee',
        password: 'test-password',
        deviceId: _deviceId,
      ),
      throwsA(isA<ApiDeviceMismatch>()),
    );
  });
  test(
    'device probes and signs in by employee ID under the configured server path',
    () async {
      const base = 'https://time.example:8088/field';
      final server = _LoginServer(base: base);
      final api = AuthApi(
        ApiClient(
          tokenStore: _Tokens(),
          onSessionLost: () {},
          dio: Dio()..httpClientAdapter = server,
        ),
      );
      expect((await api.probe(base)).apiContract, 2);
      await api.signIn(
        host: base,
        employeeId: 'EMP-042',
        password: 'test-password',
        deviceId: _deviceId,
      );
      expect(server.loginBody, {
        'employee_id': 'EMP-042',
        'password': 'test-password',
        'device_id': _deviceId,
      });
    },
  );
}
