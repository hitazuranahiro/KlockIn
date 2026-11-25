import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/auth_interceptor.dart';
import '../../../core/auth/session.dart';
import '../../attendance/data/attendance_api.dart';
import '../../home/data/home_api.dart';
import 'punch_background_sync.dart';
import 'punch_device.dart';
import 'punch_queue.dart';

bool _hasConnection(List<ConnectivityResult> network) =>
    network.any((entry) => entry != ConnectivityResult.none);

final punchConnectionProvider = Provider<Future<bool> Function()>((ref) {
  return () async => _hasConnection(await Connectivity().checkConnectivity());
});

final punchConnectivityProvider = StreamProvider<bool>((ref) async* {
  final connectivity = Connectivity();
  yield _hasConnection(await connectivity.checkConnectivity());
  yield* connectivity.onConnectivityChanged.map(_hasConnection).distinct();
});

bool get supportsOfflinePunches =>
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS);

class PunchSync {
  PunchSync(this._ref);

  final Ref _ref;
  Future<void>? _inFlight;

  Future<PunchReceipt> record(Session session, QueuedPunch punch) async {
    final account = punchQueueAccount(session);
    final queue = _ref.read(punchQueueProvider);
    await queue.add(account, punch);
    unawaited(schedulePunchBackgroundSync());
    _invalidate();
    final active = _inFlight;
    if (active != null) await active;
    await flush(onlineUuid: punch.uuid);
    final recent = await queue.recent(account);
    final saved = recent.where((row) => row.uuid == punch.uuid).firstOrNull;
    return PunchReceipt(
      saved?.state ?? PunchSyncState.pending,
      detectedAddress: saved?.detectedAddress,
      punchedAt: saved?.punchedAt,
      syncedAt: saved?.syncedAt,
    );
  }

  Future<void> flush({String? onlineUuid, bool background = false}) =>
      _inFlight ??= _flush(
        onlineUuid,
        background,
      ).whenComplete(() => _inFlight = null);

  void _invalidate() {
    _ref.invalidate(recentPunchesProvider);
    _ref.invalidate(pendingPunchCountProvider);
    _ref.invalidate(lastSuccessfulPunchSyncProvider);
  }

  Future<void> _flush(String? onlineUuid, bool background) async {
    final session = _ref.read(sessionProvider);
    if (session == null || session.user.id <= 0) return;
    var updated = false;
    try {
      if (!await _ref.read(punchConnectionProvider)()) return;
      final queue = _ref.read(punchQueueProvider);
      final account = punchQueueAccount(session);
      final dio = _ref.read(apiClientProvider).dio;
      final options = Options(
        followRedirects: false,
        extra: {
          AuthInterceptor.expectedEmployeeKey: session.user.id,
          if (background) AuthInterceptor.backgroundRequestKey: true,
        },
      );
      final device = _ref.read(punchDeviceProvider);
      final canReport = device.supportsBinding;
      final before = canReport ? await _observeQueue(queue, account) : null;
      final deviceId = canReport
          ? await _reportDeviceId(
              device,
              queuedDeviceId: background ? before?.pendingDeviceId : null,
            )
          : null;
      final startingReport = before != null && deviceId != null
          ? _publishQueueObservation(dio, session, options, deviceId, before)
          : null;
      var attempted = false;

      try {
        while (true) {
          final current = _ref.read(sessionProvider);
          if (current == null || punchQueueAccount(current) != account) break;
          final pending = await queue.pending(account);
          if (pending.isEmpty) break;
          attempted = true;

          final first = pending.first;
          if (first.uuid == onlineUuid && pending.length == 1) {
            final outcome = await _single(dio, session, options, first);
            if (outcome == null) break;
            await _applyOutcome(queue, account, first.uuid, outcome);
            updated = true;
            if (outcome.state == PunchSyncState.pending) break;
            continue;
          }

          final Response<dynamic> response;
          try {
            response = await dio.post<dynamic>(
              '${session.host}/api/v2/attendance/sync-batch/',
              data: [
                for (final punch in pending)
                  {
                    ...punch.fields,
                    'punch_selfie': base64Encode(punch.selfie!),
                  },
              ],
              options: options,
            );
          } on DioException catch (error) {
            if (error.response?.statusCode != 403) rethrow;
            final reason = _retryReason(error.response?.data);
            for (final punch in pending) {
              await queue.defer(account, punch.uuid, reason);
            }
            updated = true;
            break;
          }
          final results = (response.data is Map
              ? response.data['results']
              : null);
          if (results is! List || results.length != pending.length) break;
          var remaining = false;
          for (var index = 0; index < pending.length; index++) {
            final result = results[index];
            final punch = pending[index];
            final outcome =
                result is Map &&
                    (result['punch_uuid'] == punch.uuid ||
                        (result['punch_uuid'] == null &&
                            result['index'] == index))
                ? _outcome(result['status'], result, punch.uuid)
                : null;
            if (outcome == null) {
              remaining = true;
            } else {
              await _applyOutcome(queue, account, punch.uuid, outcome);
              updated = true;
              if (outcome.state == PunchSyncState.pending) remaining = true;
            }
          }
          if (remaining) break;
        }
      } finally {
        if (attempted && deviceId != null) {
          final after = await _observeQueue(queue, account);
          if (after != null) {
            await _publishQueueObservation(
              dio,
              session,
              options,
              deviceId,
              after,
            );
          }
        }
        if (startingReport != null) await startingReport;
      }
    } on DioException {
      // Retry with the original UUID when the API becomes reachable again.
    } catch (error) {
      debugPrint('KlockIN attendance sync deferred: ${error.runtimeType}');
    } finally {
      if (updated) {
        _invalidate();
        _ref.invalidate(homeProvider);
        _ref.invalidate(attendanceOverviewProvider);
      }
    }
  }

  Future<PunchQueueObservation?> _observeQueue(
    PunchQueue queue,
    String account,
  ) async {
    try {
      return await queue.observePending(account);
    } catch (_) {
      return null;
    }
  }

  Future<String?> _reportDeviceId(
    PunchDevice device, {
    String? queuedDeviceId,
  }) async {
    try {
      return await device.read();
    } catch (_) {
      // On a locked device, background processing can still read its queue.
      // Reuse its saved device ID when all pending rows agree.
      return queuedDeviceId;
    }
  }

  Future<void> _publishQueueObservation(
    Dio dio,
    Session session,
    Options options,
    String deviceId,
    PunchQueueObservation observation,
  ) async {
    final cancel = CancelToken();
    final timeout = Timer(const Duration(seconds: 2), cancel.cancel);
    try {
      await dio.post<dynamic>(
        '${session.host}/api/v2/attendance/device-queue/',
        data: {
          'device_id': deviceId,
          'pending_punches': observation.pendingCount,
          'observed_at': observation.observedAt.toUtc().toIso8601String(),
        },
        // Telemetry failures cannot refresh or expire the punch session.
        options: options.copyWith(
          validateStatus: (_) => true,
          responseType: ResponseType.plain,
        ),
        cancelToken: cancel,
      );
    } catch (_) {
      // The queue remains authoritative when the report cannot be delivered.
    } finally {
      timeout.cancel();
    }
  }

  Future<void> _applyOutcome(
    PunchQueue queue,
    String account,
    String uuid,
    _Outcome outcome,
  ) async {
    if (outcome.state == PunchSyncState.pending) {
      await queue.defer(account, uuid, outcome.error!);
      return;
    }
    await queue.finish(
      account,
      uuid,
      outcome.state,
      error: outcome.error,
      detectedAddress: outcome.detectedAddress,
      punchedAt: outcome.punchedAt,
      syncedAt: outcome.syncedAt,
    );
  }

  Future<_Outcome?> _single(
    Dio dio,
    Session session,
    Options options,
    QueuedPunch punch,
  ) async {
    try {
      final result = await dio.post<dynamic>(
        '${session.host}/api/v2/attendance/punch/',
        data: FormData.fromMap({
          ...punch.fields,
          'punch_selfie': MultipartFile.fromBytes(
            punch.selfie!,
            filename: 'selfie.jpg',
          ),
        }),
        options: options,
      );
      return _outcome(result.statusCode, result.data, punch.uuid);
    } on DioException catch (error) {
      return _outcome(
        error.response?.statusCode,
        error.response?.data,
        punch.uuid,
      );
    }
  }
}

class _Outcome {
  const _Outcome(
    this.state, {
    this.error,
    this.detectedAddress,
    this.punchedAt,
    this.syncedAt,
  });

  final PunchSyncState state;
  final String? error;
  final String? detectedAddress;
  final DateTime? punchedAt;
  final DateTime? syncedAt;
}

_Outcome? _outcome(Object? status, Object? body, String uuid) {
  if ((status == 200 || status == 201) &&
      body is Map &&
      body['punch_uuid'] == uuid &&
      body['sync_status'] == 'SYNCED') {
    final value = body['detected_address'];
    final address = value is String ? value.trim() : '';
    return _Outcome(
      body['projection_status'] == 'PENDING'
          ? PunchSyncState.review
          : PunchSyncState.synced,
      detectedAddress: address.isEmpty ? null : address,
      punchedAt: _receiptTime(body['punched_at']),
      syncedAt:
          _receiptTime(body['server_sync_timestamp']) ??
          _receiptTime(body['server_receive_timestamp']) ??
          DateTime.now().toUtc(),
    );
  }
  // Authorization can recover after signing in again, a device reset, or
  // an HR permissions change. Only the explicit refusal of this UUID's
  // captured coordinates is a terminal 403.
  if (status == 403 &&
      (body is! Map ||
          body['punch_uuid'] != uuid ||
          body['code'] != 'outside_geofence')) {
    return _Outcome(PunchSyncState.pending, error: _retryReason(body));
  }
  if (status == 400 ||
      status == 403 ||
      status == 409 ||
      status == 413 ||
      status == 422) {
    final detail = body is Map ? body['detail'] : null;
    return _Outcome(
      PunchSyncState.rejected,
      error: detail is String
          ? detail
          : 'The server declined this punch ($status).',
    );
  }
  return null;
}

String _retryReason(Object? body) => switch (body is Map
    ? body['code']
    : null) {
  'device_mismatch' =>
    'Ask HR to reset the linked device, then sign in here and sync again.',
  'device_not_enrolled' => 'Sign in on this device, then sync again.',
  'employee_required' =>
    'Ask HR to check your employee account, then sync again.',
  _ => 'The server did not authorize this upload. Sign in again or contact HR.',
};

final punchSyncProvider = Provider<PunchSync>(PunchSync.new);

DateTime? _receiptTime(Object? value) =>
    value is String ? DateTime.tryParse(value)?.toUtc() : null;
