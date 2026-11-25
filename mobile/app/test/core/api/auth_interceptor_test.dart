// Modified for KlockIN by Tomeku, 2026-11-25.
/// Refresh behaviour, which is the app's highest-consequence logic and the
/// part that cannot be checked by hand: the failure only shows up when several
/// requests expire at the same moment.
library;

import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/auth_interceptor.dart';
import 'package:klockin/core/auth/session_lock.dart';
import 'package:klockin/core/auth/token_store.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// An in-memory TokenStore. The real one talks to the Keychain, which is not
/// available in a headless test and is not what these tests are about.
class FakeTokenStore implements TokenStore {
  FakeTokenStore(this._session);

  StoredSession? _session;
  int writes = 0;

  @override
  Future<StoredSession?> read() async => _session;

  @override
  Future<void> write(StoredSession session) async {
    writes++;
    _session = session;
  }

  @override
  Future<void> clear() async => _session = null;
}

/// Stands in for the server. Counts refreshes so the single-flight guard can
/// be asserted rather than assumed.
class FakeServer {
  FakeServer({this.refreshSucceeds = true, this.onProtected});

  final bool refreshSucceeds;
  final void Function()? onProtected;
  int refreshCalls = 0;
  int protectedCalls = 0;
  final List<String> tokensSeen = [];

  Dio build() {
    final dio = Dio();
    dio.httpClientAdapter = _Adapter(this);
    return dio;
  }
}

class _Adapter implements HttpClientAdapter {
  _Adapter(this.server);
  final FakeServer server;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (options.path.contains('/auth/refresh/')) {
      server.refreshCalls++;
      await Future<void>.delayed(const Duration(milliseconds: 20));
      if (!server.refreshSucceeds) {
        return ResponseBody.fromString(
          '{"detail":"invalid"}',
          401,
          headers: {
            Headers.contentTypeHeader: [Headers.jsonContentType],
          },
        );
      }
      return ResponseBody.fromString(
        '{"access":"access-2","refresh":"refresh-2"}',
        200,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    }

    server.protectedCalls++;
    server.onProtected?.call();
    final auth = options.headers['Authorization'] as String?;
    if (auth != null) server.tokensSeen.add(auth);

    // The first token is expired; the rotated one is accepted.
    final expired = auth == null || auth.endsWith('access-1');
    return ResponseBody.fromString(
      expired ? '{"detail":"expired"}' : '{"ok":true}',
      expired ? 401 : 200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }
}

Dio buildClient(
  FakeServer server,
  FakeTokenStore store, {
  required void Function() onSessionLost,
  SessionLock? lock,
}) {
  final dio = Dio(BaseOptions(baseUrl: 'https://hr.example.com/api/v1'));
  dio.httpClientAdapter = _Adapter(server);
  dio.interceptors.add(
    AuthInterceptor(
      tokenStore: store,
      refreshClient: server.build(),
      onSessionLost: onSessionLost,
      sessionLock: lock,
    ),
  );
  return dio;
}

StoredSession seed() => const StoredSession(
  host: 'https://hr.example.com',
  accessToken: 'access-1',
  refreshToken: 'refresh-1',
);

void main() {
  test('attaches the stored access token', () async {
    final store = FakeTokenStore(seed());
    final server = FakeServer();
    final dio = buildClient(server, store, onSessionLost: () {});

    await dio.get<dynamic>('/anything');

    expect(server.tokensSeen.first, 'Bearer access-1');
  });

  test('a 401 refreshes once and replays the request', () async {
    final store = FakeTokenStore(seed());
    final server = FakeServer();
    final dio = buildClient(server, store, onSessionLost: () {});

    final response = await dio.get<dynamic>('/anything');

    expect(response.statusCode, 200);
    expect(server.refreshCalls, 1);
    expect(store.writes, 1, reason: 'the rotated tokens must be persisted');
  });

  test('the rotated refresh token replaces the spent one', () async {
    // Rotation is on server-side and the spent token is blacklisted, so
    // keeping the old one signs the user out at the next refresh.
    final store = FakeTokenStore(seed());
    final server = FakeServer();
    final dio = buildClient(server, store, onSessionLost: () {});

    await dio.get<dynamic>('/anything');

    final session = await store.read();
    expect(session!.accessToken, 'access-2');
    expect(session.refreshToken, 'refresh-2');
    expect(
      session.host,
      'https://hr.example.com',
      reason: 'the host must survive a refresh',
    );
  });

  test('concurrent 401s trigger exactly one refresh', () async {
    // The regression this guard exists for. Home fires several requests at
    // once; without single-flight each 401 starts its own refresh, and
    // rotation means all but one of those fail and sign the user out.
    final store = FakeTokenStore(seed());
    final server = FakeServer();
    final dio = buildClient(server, store, onSessionLost: () {});

    await Future.wait([
      dio.get<dynamic>('/one'),
      dio.get<dynamic>('/two'),
      dio.get<dynamic>('/three'),
      dio.get<dynamic>('/four'),
    ]);

    expect(
      server.refreshCalls,
      1,
      reason: 'six concurrent refreshes would invalidate each other',
    );
  });

  test('a failed refresh reports the session lost and does not loop', () async {
    // A password change invalidates refresh tokens server-side, so this is a
    // real state rather than a blip: it must land on sign-in, not retry.
    final store = FakeTokenStore(seed());
    final server = FakeServer(refreshSucceeds: false);
    var lost = 0;
    final dio = buildClient(server, store, onSessionLost: () => lost++);

    await expectLater(
      dio.get<dynamic>('/anything'),
      throwsA(isA<DioException>()),
    );

    expect(lost, 1);
    expect(server.refreshCalls, 1, reason: 'one attempt, then give up');
    expect(await store.read(), isNull, reason: 'the dead session is cleared');
  });

  test(
    'a background 401 refreshes and replays with rotated credentials',
    () async {
      final store = FakeTokenStore(seed());
      final server = FakeServer();
      final dio = buildClient(
        server,
        store,
        onSessionLost: () => fail('Unexpected session loss'),
      );

      final response = await dio.post<dynamic>(
        '/anything',
        data: {'punch_uuid': 'queued-punch'},
        options: Options(extra: {AuthInterceptor.backgroundRequestKey: true}),
      );

      expect(response.statusCode, 200);
      expect(server.refreshCalls, 1);
      expect(server.tokensSeen, ['Bearer access-1', 'Bearer access-2']);
      expect((await store.read())!.refreshToken, 'refresh-2');
    },
  );

  test(
    'an expired background refresh retains the session for foreground handling',
    () async {
      final store = FakeTokenStore(seed());
      final server = FakeServer(refreshSucceeds: false);
      final dio = buildClient(
        server,
        store,
        onSessionLost: () => fail('Worker signed out foreground'),
      );

      await expectLater(
        dio.post<dynamic>(
          '/anything',
          options: Options(extra: {AuthInterceptor.backgroundRequestKey: true}),
        ),
        throwsA(isA<DioException>()),
      );
      expect(server.refreshCalls, 1);
      expect((await store.read())!.refreshToken, 'refresh-1');
    },
  );

  test(
    'two clients with independent SQLite connections rotate only once',
    () async {
      sqfliteFfiInit();
      final directory = await Directory.systemTemp.createTemp(
        'klockin-session-',
      );
      addTearDown(() => directory.delete(recursive: true));
      SqliteSessionLock openLock() => SqliteSessionLock(
        factory: databaseFactoryFfi,
        databasePath: () async => '${directory.path}/refresh.sqlite',
      );
      final store = FakeTokenStore(seed());
      final server = FakeServer();
      final foreground = buildClient(
        server,
        store,
        onSessionLost: () {},
        lock: openLock(),
      );
      final background = buildClient(
        server,
        store,
        onSessionLost: () {},
        lock: openLock(),
      );

      final responses = await Future.wait([
        foreground.get<dynamic>('/foreground'),
        background.post<dynamic>(
          '/background',
          options: Options(extra: {AuthInterceptor.backgroundRequestKey: true}),
        ),
      ]);

      expect(responses.map((response) => response.statusCode), [200, 200]);
      expect(server.refreshCalls, 1);
      expect(store.writes, 1);
    },
  );

  test(
    'an earlier request cannot refresh or replay using another account',
    () async {
      final requested = Completer<void>();
      final release = Completer<void>();
      final store = FakeTokenStore(seed());
      final lock = MemorySessionLock();
      final accountSwitch = lock.run(() async {
        await release.future;
        await store.write(
          const StoredSession(
            host: 'https://hr.example.com',
            accessToken: 'other-access',
            refreshToken: 'other-refresh',
            employeeId: 42,
          ),
        );
      });
      final server = FakeServer(onProtected: requested.complete);
      final dio = buildClient(
        server,
        store,
        onSessionLost: () => fail('Lost the new account'),
        lock: lock,
      );

      final response = dio.get<dynamic>('/anything');
      final handled = expectLater(response, throwsA(isA<DioException>()));
      await requested.future;
      release.complete();
      await accountSwitch;
      await handled;

      expect(server.refreshCalls, 0);
      expect(server.protectedCalls, 1);
      expect((await store.read())!.employeeId, 42);
    },
  );

  test(
    'an unrelated origin never receives or refreshes the stored token',
    () async {
      final store = FakeTokenStore(seed());
      final server = FakeServer();
      final dio = buildClient(
        server,
        store,
        onSessionLost: () => fail('Lost the original account'),
      );

      await expectLater(
        dio.get<dynamic>('https://unrelated.example.com/anything'),
        throwsA(isA<DioException>()),
      );
      expect(server.tokensSeen, isEmpty);
      expect(server.refreshCalls, 0);
    },
  );
}
