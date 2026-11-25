// Modified for KlockIN by Tomeku, 2026-11-25.
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/api_failure.dart';
import '../../../core/api/auth_interceptor.dart';
import 'auth_models.dart';

const int kMinimumApiContract = 2;

class AuthApi {
  AuthApi(this._client);

  final ApiClient _client;

  Future<ServerInfo> probe(String host) async {
    if (!kDebugMode && !host.startsWith('https://')) {
      throw const ApiIncompatibleServer('Use HTTPS to connect to KlockIN.');
    }
    final body = await _get(host, '/health/');
    final info = body is Map<String, dynamic>
        ? ServerInfo.fromJson(body)
        : null;
    if (info == null) throw const ApiIncompatibleServer();
    if (info.apiContract < kMinimumApiContract) {
      throw const ApiIncompatibleServer(
        'Update the KlockIN server to enable mobile attendance.',
      );
    }
    return info;
  }

  Future<Object?> _get(String host, String path) async {
    try {
      final response = await _client.dio.get<dynamic>(
        '$host$path',
        options: Options(
          extra: {AuthInterceptor.skipAuthKey: true},
          followRedirects: false,
          // A wrong host often answers with something; inspect it rather than
          // letting the status alone raise.
          validateStatus: (_) => true,
        ),
      );
      return response.data;
    } on DioException catch (e) {
      final failure = e.error;
      throw failure is ApiFailure ? failure : const ApiNetwork();
    }
  }

  Future<SignInResult> signIn({
    required String host,
    String? username,
    String? employeeId,
    required String password,
    String? deviceId,
  }) async {
    if (!kDebugMode && !host.startsWith('https://')) {
      throw const ApiIncompatibleServer('Use HTTPS to connect to KlockIN.');
    }
    try {
      final response = await _client.dio.post<dynamic>(
        '$host$kApiPrefix/auth/login/',
        data: {
          if (username != null) 'username': username,
          if (employeeId != null) 'employee_id': employeeId,
          'password': password,
          if (deviceId != null) 'device_id': deviceId,
        },
        options: Options(
          extra: {AuthInterceptor.skipAuthKey: true},
          followRedirects: false,
        ),
      );

      final body = response.data;
      final result = body is Map<String, dynamic>
          ? SignInResult.fromJson(body)
          : null;
      if (result == null) throw const ApiIncompatibleServer();
      return result;
    } on DioException catch (e) {
      final failure = e.error;
      throw failure is ApiFailure ? failure : const ApiUnknown();
    }
  }
}
