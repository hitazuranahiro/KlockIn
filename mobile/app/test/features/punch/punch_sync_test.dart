import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/api_client.dart';
import 'package:klockin/core/api/auth_interceptor.dart';
import 'package:klockin/core/auth/session.dart';
import 'package:klockin/core/auth/token_store.dart';
import 'package:klockin/features/auth/data/auth_models.dart';
import 'package:klockin/features/punch/data/punch_device.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';
import 'package:klockin/features/punch/data/punch_sync.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../support/punch_evidence.dart';

const _session = Session(
  host: 'https://time.example',
  user: SignedInUser(id: 4, fullName: 'Employee'),
  capabilities: Capabilities.empty,
  isCleartext: false,
  geoFencingEnabled: false,
  faceDetectionEnabled: false,
);

class _Session extends SessionController {
  @override
  Session? build() => _session;
}

class _Tokens implements TokenStore {
  @override
  Future<StoredSession?> read() async => const StoredSession(
    host: 'https://time.example',
    employeeId: 4,
    accessToken: 'test-access',
    refreshToken: 'test-refresh',
  );
  @override
  Future<void> write(StoredSession session) async {}
  @override
  Future<void> clear() async {}
}

class _BatchServer implements HttpClientAdapter {
  final calls = <List<String>>[];

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    expect(
      options.uri.toString(),
      'https://time.example/api/v2/attendance/sync-batch/',
    );
    expect(options.headers['Authorization'], 'Bearer test-access');
    final payload =
        jsonDecode(await utf8.decoder.bind(requestStream!).join()) as List;
    calls.add([for (final punch in payload) punch['punch_uuid'] as String]);
    for (final punch in payload) {
      expect(punch['punch_selfie'], 'AQID');
      expect(punch['gps_long'], '121.000000');
      expect(punch['punched_at'], endsWith('Z'));
      expect(punch.containsKey('detected_address'), isFalse);
    }

    return ResponseBody.fromString(
      jsonEncode({
        'results': [
          for (final punch in payload)
            switch (punch['punch_uuid']) {
              'older' => {
                'status': 201,
                'punch_uuid': 'older',
                'sync_status': 'SYNCED',
                'projection_status': 'LINKED',
                'detected_address': '  Makati, Metro Manila  ',
                'punched_at': '2026-11-25T08:00:04Z',
                'server_receive_timestamp': '2026-11-25T09:55:02Z',
                'server_sync_timestamp': '2026-11-25T10:00:03Z',
              },
              'later' when calls.length == 1 => {
                'status': 503,
                'punch_uuid': 'later',
              },
              'later' => {
                'status': 200,
                'punch_uuid': 'later',
                'sync_status': 'SYNCED',
                'projection_status': 'PENDING',
                'detected_address': '',
              },
              _ => {
                'status': 409,
                'punch_uuid': 'duplicate',
                'detail': 'Punch is too close to another one.',
              },
            },
        ],
      }),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }
}

class _ReportingDevice extends PunchDevice {
  _ReportingDevice({required this.locked});

  final bool locked;

  @override
  bool get supportsBinding => true;

  @override
  Future<String> read() async {
    if (locked) throw StateError('Keychain is locked');
    return 'device';
  }
}

class _ReportingServer implements HttpClientAdapter {
  _ReportingServer({required this.background});

  final bool background;
  final counts = <int>[];
  final dates = <DateTime>[];
  final uploadedBatches = <int>[];
  final _firstReport = Completer<ResponseBody>();
  int refreshCalls = 0;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (options.uri.path.endsWith('/auth/refresh/')) {
      refreshCalls++;
      return ResponseBody.fromString('{}', 401);
    }
    expect(options.uri.origin, _session.host);
    expect(options.followRedirects, isFalse);
    expect(options.headers['Authorization'], 'Bearer test-access');
    expect(
      options.extra[AuthInterceptor.expectedEmployeeKey],
      _session.user.id,
    );
    expect(
      options.extra[AuthInterceptor.backgroundRequestKey],
      background ? true : null,
    );
    final payload = jsonDecode(await utf8.decoder.bind(requestStream!).join());
    if (options.uri.path.endsWith('/device-queue/')) {
      final report = payload as Map<String, dynamic>;
      expect(
        report.keys,
        unorderedEquals(['device_id', 'pending_punches', 'observed_at']),
      );
      expect(report['device_id'], 'device');
      final count = report['pending_punches'] as int;
      counts.add(count);
      dates.add(DateTime.parse(report['observed_at'] as String));
      if (counts.length == 1) return _firstReport.future;
      // Release the start response after the final report has arrived.
      // A failed older observation must not prevent processing or expiry isolation.
      _firstReport.complete(
        ResponseBody.fromString('denied', background ? 403 : 401),
      );
      return ResponseBody.fromString('', 204);
    }
    expect(options.uri.path, '/api/v2/attendance/sync-batch/');
    final punches = payload as List;
    uploadedBatches.add(punches.length);
    return ResponseBody.fromString(
      jsonEncode({
        'results': [
          for (final punch in punches)
            {
              'status': 201,
              'punch_uuid': punch['punch_uuid'],
              'sync_status': 'SYNCED',
            },
        ],
      }),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }
}

class _PolicyServer implements HttpClientAdapter {
  _PolicyServer(this.reason, {this.refuseWholeBatch = false});

  final String reason;
  final bool refuseWholeBatch;
  bool recovered = false;
  int requests = 0;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    expect(
      ++requests,
      lessThanOrEqualTo(2),
      reason: 'a refusal must not busy-loop',
    );
    final multipart = options.uri.path.endsWith('/punch/');
    final bytes = await requestStream!.expand((chunk) => chunk).toList();
    final text = utf8.decode(bytes);
    final Map<String, dynamic> payload;
    if (multipart) {
      payload = Map<String, dynamic>.fromEntries(
        (options.data as FormData).fields,
      );
      expect(text, contains('\x01\x02\x03'));
    } else {
      payload = (jsonDecode(text) as List).single as Map<String, dynamic>;
      expect(payload['punch_selfie'], 'AQID');
    }
    expect(payload['punch_uuid'], 'protected-punch');
    expect(payload['gps_lat'], '14.500000');
    expect(payload['gps_long'], '121.000000');
    expect(payload['device_id'], 'phone');

    final response = {
      'punch_uuid': 'protected-punch',
      if (recovered) 'sync_status': 'SYNCED' else 'code': reason,
      if (!recovered)
        'detail': 'The punch is outside the permitted work location.',
    };
    final code = recovered ? 201 : 403;
    final wholeBatch = !recovered && refuseWholeBatch;
    return ResponseBody.fromString(
      jsonEncode(
        multipart || wholeBatch
            ? response
            : {
                'results': [
                  {'status': code, ...response},
                ],
              },
      ),
      multipart || wholeBatch ? code : 200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }
}

void main() {
  for (final scenario in [
    (
      reason: 'device_mismatch',
      online: true,
      wholeBatch: false,
      terminal: false,
    ),
    (
      reason: 'employee_required',
      online: false,
      wholeBatch: false,
      terminal: false,
    ),
    (
      reason: 'permission_denied',
      online: false,
      wholeBatch: true,
      terminal: false,
    ),
    (
      reason: 'outside_geofence',
      online: true,
      wholeBatch: false,
      terminal: true,
    ),
  ]) {
    test(
      '403 ${scenario.reason} protects evidence until terminal or recovered',
      () async {
        sqfliteFfiInit();
        final db = await SqlitePunchQueue.open(
          databaseFactoryFfi,
          inMemoryDatabasePath,
          testPunchCipher,
        );
        addTearDown(db.close);
        final queue = SqlitePunchQueue(Future.value(db), testPunchCipher);
        final server = _PolicyServer(
          scenario.reason,
          refuseWholeBatch: scenario.wholeBatch,
        );
        final api = ApiClient(
          tokenStore: _Tokens(),
          onSessionLost: () {},
          dio: Dio()..httpClientAdapter = server,
        );
        final container = ProviderContainer(
          overrides: [
            punchQueueProvider.overrideWithValue(queue),
            sessionProvider.overrideWith(_Session.new),
            apiClientProvider.overrideWithValue(api),
            punchConnectionProvider.overrideWithValue(() async => true),
          ],
        );
        addTearDown(container.dispose);
        final account = punchQueueAccount(_session);
        final sync = container.read(punchSyncProvider);
        final punch = QueuedPunch(
          uuid: 'protected-punch',
          isClockingIn: true,
          at: DateTime.utc(2026, 11, 25, 8),
          deviceId: 'phone',
          latitude: 14.5,
          longitude: 121,
          selfie: Uint8List.fromList([1, 2, 3]),
        );
        if (scenario.online) {
          await sync.record(_session, punch);
        } else {
          await queue.add(account, punch);
          await sync.flush();
        }
        expect(server.requests, 1);
        final row = (await db.query('punches')).single;
        final receipt = (await queue.recent(account)).single;
        if (scenario.terminal) {
          expect(receipt.state, PunchSyncState.rejected);
          expect(receipt.error, contains('outside the permitted'));
          expect(row['evidence'], isNull);
          return;
        }
        expect(receipt.state, PunchSyncState.pending);
        expect(
          receipt.error,
          anyOf(contains('sync again'), contains('authorize this upload')),
        );
        expect(row['evidence'], isA<Uint8List>());
        final saved = (await queue.pending(account)).single;
        expect(saved.selfie, punch.selfie);
        expect(saved.fields, punch.fields);
        server.recovered = true;
        await sync.flush();
        expect(server.requests, 2);
        expect(await queue.pendingCount(account), 0);
        final synced = (await queue.recent(account)).single;
        expect(synced.state, PunchSyncState.synced);
        expect(synced.error, isNull);
        expect((await db.query('punches')).single['evidence'], isNull);
      },
    );
  }

  test(
    'batch sync preserves originals, applies per-item receipts and retries pending UUIDs',
    () async {
      sqfliteFfiInit();
      final db = await SqlitePunchQueue.open(
        databaseFactoryFfi,
        inMemoryDatabasePath,
        testPunchCipher,
      );
      addTearDown(db.close);
      final queue = SqlitePunchQueue(Future.value(db), testPunchCipher);
      final account = punchQueueAccount(_session);
      QueuedPunch punch(String uuid, int hour) => QueuedPunch(
        uuid: uuid,
        isClockingIn: hour != 9,
        at: DateTime.utc(2026, 11, 25, hour),
        deviceId: 'device',
        latitude: 14.5,
        longitude: 121.0,
        selfie: Uint8List.fromList([1, 2, 3]),
      );
      await queue.add(account, punch('duplicate', 10));
      await queue.add(account, punch('later', 9));
      await queue.add(account, punch('older', 8));
      final server = _BatchServer();
      final api = ApiClient(
        tokenStore: _Tokens(),
        onSessionLost: () {},
        dio: Dio()..httpClientAdapter = server,
      );
      var connected = false;
      final container = ProviderContainer(
        overrides: [
          punchQueueProvider.overrideWithValue(queue),
          sessionProvider.overrideWith(_Session.new),
          apiClientProvider.overrideWithValue(api),
          punchConnectionProvider.overrideWithValue(() async => connected),
        ],
      );
      addTearDown(container.dispose);

      await container.read(punchSyncProvider).flush();
      expect(server.calls, isEmpty);

      connected = true;
      await container.read(punchSyncProvider).flush();
      expect(server.calls.single, ['older', 'later', 'duplicate']);
      expect(await queue.pendingCount(account), 1);
      expect(
        await queue.lastSuccessfulSync(account),
        DateTime.utc(2026, 11, 25, 10, 0, 3),
      );
      expect((await queue.recent(account)).first.error, contains('too close'));

      await container.read(punchSyncProvider).flush();
      expect(server.calls.last, ['later']);
      expect(await queue.pendingCount(account), 0);
      final recent = {
        for (final punch in await queue.recent(account)) punch.uuid: punch,
      };
      expect(recent['later']!.state, PunchSyncState.review);
      expect(recent['later']!.detectedAddress, isNull);
      expect(recent['older']!.detectedAddress, 'Makati, Metro Manila');
    },
  );

  for (final background in [false, true]) {
    test('queue reporting counts pending work and isolates denied '
        '${background ? 'worker' : 'foreground'} observations', () async {
      sqfliteFfiInit();
      final db = await SqlitePunchQueue.open(
        databaseFactoryFfi,
        inMemoryDatabasePath,
        testPunchCipher,
      );
      addTearDown(db.close);
      final queue = SqlitePunchQueue(Future.value(db), testPunchCipher);
      final account = punchQueueAccount(_session);
      QueuedPunch row(
        String uuid, {
        PunchSyncState state = PunchSyncState.pending,
      }) => QueuedPunch(
        uuid: uuid,
        isClockingIn: true,
        at: DateTime.utc(2026, 11, 25),
        deviceId: 'device',
        latitude: 14.5,
        longitude: 121,
        selfie: Uint8List.fromList([1, 2, 3]),
        state: state,
      );

      for (var i = 0; i < 6; i++) {
        await queue.add(account, row('queued-$i'));
      }
      await queue.add('other-account', row('other-account'));
      await queue.add(
        account,
        row('already-synced', state: PunchSyncState.synced),
      );
      final server = _ReportingServer(background: background);
      var lostSessions = 0;
      final api = ApiClient(
        tokenStore: _Tokens(),
        onSessionLost: () => lostSessions++,
        dio: Dio()..httpClientAdapter = server,
        refreshDio: Dio()..httpClientAdapter = server,
      );
      final container = ProviderContainer(
        overrides: [
          punchQueueProvider.overrideWithValue(queue),
          sessionProvider.overrideWith(_Session.new),
          apiClientProvider.overrideWithValue(api),
          punchConnectionProvider.overrideWithValue(() async => true),
          punchDeviceProvider.overrideWithValue(
            _ReportingDevice(locked: background),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(punchSyncProvider).flush(background: background);

      expect(server.counts, [6, 0]);
      expect(server.dates.every((date) => date.isUtc), isTrue);
      expect(server.dates.last.isBefore(server.dates.first), isFalse);
      expect(server.uploadedBatches, [5, 1]);
      expect(server.refreshCalls, 0);
      expect(lostSessions, 0);
      expect(await queue.pendingCount(account), 0);
      expect(await queue.pendingCount('other-account'), 1);
    });
  }
}
