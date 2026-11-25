import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/auth/session.dart';
import '../../punch/data/punch_queue.dart';
import 'confirmed_work_store.dart';
import 'home_models.dart';

class HomeApi {
  HomeApi(this._dio);

  final Dio _dio;

  Future<HomeData> fetch() async {
    try {
      final response = await _dio.get<dynamic>('/mobile/home/');
      final body = response.data;
      if (body is! Map<String, dynamic>) throw const ApiIncompatibleServer();
      return HomeData.fromJson(body);
    } on DioException catch (e) {
      final failure = e.error;
      throw failure is ApiFailure ? failure : const ApiUnknown();
    }
  }

  Future<BreakPolicy> changeBreak(BreakAction action) async {
    try {
      final response = await _dio.post<dynamic>(
        '/mobile/break/',
        data: {'action': action.name},
      );
      final policy = BreakPolicy.fromJson(response.data);
      if (policy == null) throw const ApiIncompatibleServer();
      return policy;
    } on DioException catch (e) {
      final failure = e.error;
      throw failure is ApiFailure ? failure : const ApiUnknown();
    }
  }
}

final homeApiProvider = Provider<HomeApi>(
  (ref) => HomeApi(ref.watch(apiClientProvider).dio),
);

/// Live Home data and an account-scoped confirmation for offline display.
final homeProvider = FutureProvider<HomeData>((ref) async {
  final session = ref.watch(sessionProvider);
  final home = await ref.watch(homeApiProvider).fetch();
  final confirmed = home.confirmedWork;
  if (!kIsWeb &&
      ref.mounted &&
      session != null &&
      session.user.id > 0 &&
      session.user.id == home.user.id &&
      identical(session, ref.read(sessionProvider))) {
    final account = punchQueueAccount(session);
    final store = ref.read(confirmedWorkStoreProvider);
    await Future.wait([
      if (confirmed != null) store.save(account, confirmed),
      store.saveGeofence(account, home.geofence),
    ]);
    if (ref.mounted) {
      ref.invalidate(confirmedWorkProvider(account));
      ref.invalidate(cachedGeofenceProvider(account));
    }
  }
  return home;
});
