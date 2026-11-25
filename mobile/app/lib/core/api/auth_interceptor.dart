// Modified for KlockIN by Tomeku, 2026-11-25.
import 'dart:async';

import 'package:dio/dio.dart';

import '../auth/session_lock.dart';
import '../auth/token_store.dart';
import 'api_failure.dart';
import 'host.dart';

typedef OnSessionLost = void Function();
typedef _RequestSession = ({String host, int? employeeId});

class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor({
    required this.tokenStore,
    required this.refreshClient,
    required this.onSessionLost,
    SessionLock? sessionLock,
  }) : _lock = sessionLock ?? MemorySessionLock();

  final TokenStore tokenStore;

  /// A bare client keeps refresh and replay out of the interceptor queues.
  final Dio refreshClient;
  final OnSessionLost onSessionLost;
  final SessionLock _lock;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (options.extra[skipAuthKey] == true) return handler.next(options);

    final session = await tokenStore.read();
    final expected = options.extra[expectedEmployeeKey];
    final belongsToSession =
        session != null && isWithinServerBase(options.uri, session.host);
    if (expected != null &&
        (!belongsToSession || session?.employeeId != expected)) {
      return handler.reject(
        DioException(
          requestOptions: options,
          error: const ApiUnauthenticated(),
        ),
      );
    }
    if (belongsToSession && session != null) {
      options.extra[_requestSessionKey] = (
        host: session.host,
        employeeId: session.employeeId,
      );
      options.headers['Authorization'] = 'Bearer ${session.accessToken}';
      options.followRedirects = false;
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    final scope = options.extra[_requestSessionKey];
    if (err.response?.statusCode != 401 ||
        scope is! _RequestSession ||
        options.extra[_retriedKey] == true) {
      return handler.next(err);
    }

    final StoredSession? refreshed;
    try {
      refreshed = await _lock.run(
        () => _currentOrRefreshed(
          scope,
          options.headers['Authorization'],
          background: options.extra[backgroundRequestKey] == true,
        ),
      );
    } on Exception {
      // Network and lock failures leave the saved session and queue intact.
      return handler.next(err);
    }

    if (refreshed == null) return handler.next(err);

    // Check again after yielding the lock. A sign-out or account switch can
    // run while the other Flutter engine finishes handling this response.
    final current = await tokenStore.read();
    if (!_isCurrent(current, scope)) return handler.next(err);

    options.extra[_retriedKey] = true;
    options.headers['Authorization'] = 'Bearer ${current!.accessToken}';
    final body = options.data;
    if (body is FormData) options.data = body.clone();
    try {
      final response = await refreshClient.fetch<dynamic>(options);
      handler.resolve(response);
    } on DioException catch (error) {
      handler.next(error);
    }
  }

  Future<StoredSession?> _currentOrRefreshed(
    _RequestSession scope,
    Object? sentAuthorization, {
    required bool background,
  }) async {
    final current = await tokenStore.read();
    if (!_isCurrent(current, scope)) return null;
    final session = current!;

    // A request from either engine may have completed the rotation while
    // this one was waiting for the lock.
    if ('Bearer ${session.accessToken}' != sentAuthorization) return session;
    if (session.refreshToken.isEmpty) {
      await _expireForeground(background);
      return null;
    }

    final Response<dynamic> response;
    final cancel = CancelToken();
    final deadline = Timer(const Duration(seconds: 20), cancel.cancel);
    try {
      response = await refreshClient.post<dynamic>(
        '${session.host}/api/v1/auth/refresh/',
        data: {'refresh': session.refreshToken},
        options: Options(followRedirects: false),
        cancelToken: cancel,
      );
    } on DioException catch (error) {
      final status = error.response?.statusCode;
      if (status != 400 && status != 401) rethrow;
      await _expireForeground(background);
      return null;
    } finally {
      deadline.cancel();
    }

    final body = response.data;
    if (body is! Map) return null;
    final access = body['access'];
    if (access is! String || access.isEmpty) return null;
    final rotated = body['refresh'];
    await tokenStore.write(
      session.copyWith(
        accessToken: access,
        refreshToken: rotated is String && rotated.isNotEmpty
            ? rotated
            : session.refreshToken,
      ),
    );
    final saved = await tokenStore.read();
    return _isCurrent(saved, scope) && saved?.accessToken == access
        ? saved
        : null;
  }

  Future<void> _expireForeground(bool background) async {
    // A background worker cannot route the foreground UI. Keep its pending
    // work and let the foreground request handle a confirmed expired session.
    if (background) return;
    await tokenStore.clear();
    onSessionLost();
  }

  static bool _isCurrent(StoredSession? session, _RequestSession scope) =>
      session?.host == scope.host && session?.employeeId == scope.employeeId;

  static const backgroundRequestKey = 'klockin.backgroundRequest';
  static const expectedEmployeeKey = 'klockin.expectedEmployee';
  static const skipAuthKey = 'horilla.skipAuth';
  static const _requestSessionKey = 'klockin.requestSession';
  static const _retriedKey = 'horilla.retried';
}
