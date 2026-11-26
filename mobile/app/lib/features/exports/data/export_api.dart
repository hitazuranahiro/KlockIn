import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/api/error_interceptor.dart';
import '../../../core/auth/session.dart';
import 'export_models.dart';

class ExportApi {
  ExportApi(this._dio);

  static const preferencesPath = '/mobile/export-preferences/';

  final Dio _dio;

  Future<ExportSettings> fetchSettings(ExportDocumentType type) async {
    try {
      final response = await _dio.get<dynamic>(preferencesPath);
      return _settings(type, response.data);
    } on DioException catch (error) {
      throw _failure(error);
    }
  }

  Future<ExportSettings> saveSettings(
    ExportDocumentType type,
    ExportSettings settings,
  ) async {
    try {
      final response = await _dio.patch<dynamic>(
        preferencesPath,
        data: {type.preferenceKey: settings.toPreferences(type)},
      );
      return _settings(type, response.data);
    } on DioException catch (error) {
      throw _failure(error);
    }
  }

  Future<ExportPdfDocument> fetchPdf(
    ExportTarget target,
    ExportSettings settings,
  ) async {
    try {
      final response = await _dio.get<List<int>>(
        target.path,
        queryParameters: settings.toPdfQuery(target),
        options: Options(
          headers: {'Accept': 'application/pdf'},
          responseType: ResponseType.bytes,
        ),
      );

      final bytes = response.data;
      const pdfHeader = [0x25, 0x50, 0x44, 0x46, 0x2d]; // %PDF-
      if (bytes == null ||
          bytes.length < pdfHeader.length ||
          !List.generate(
            pdfHeader.length,
            (index) => bytes[index] == pdfHeader[index],
          ).every((matches) => matches)) {
        throw const ApiUnknown('The server did not return a PDF.');
      }

      return ExportPdfDocument(
        bytes: bytes is Uint8List ? bytes : Uint8List.fromList(bytes),
        filename: _filename(
          response.headers.value('content-disposition'),
          target.fallbackFilename,
        ),
      );
    } on DioException catch (error) {
      throw _failure(error);
    }
  }

  ExportSettings _settings(ExportDocumentType type, Object? body) {
    if (body is! Map || body[type.preferenceKey] is! Map<String, dynamic>) {
      throw const ApiIncompatibleServer();
    }
    return ExportSettings.fromJson(
      type,
      body[type.preferenceKey] as Map<String, dynamic>,
    );
  }

  static ApiFailure _failure(DioException error) {
    final failure = error.error;
    return failure is ApiFailure
        ? failure
        : ErrorInterceptor().mapFailure(error);
  }

  static String _filename(String? header, String fallback) {
    if (header == null) return fallback;
    final encoded = RegExp(
      r"filename\*=UTF-8''([^;]+)",
      caseSensitive: false,
    ).firstMatch(header)?.group(1);
    String? name;
    if (encoded != null) {
      try {
        name = Uri.decodeComponent(encoded.trim());
      } on FormatException {
        // Fall back to the regular filename parameter if it is present.
      } on ArgumentError {
        // Malformed percent encoding is ignored.
      }
    }
    final ordinary = RegExp(
      r'filename=(?:"([^"]+)"|([^;]+))',
      caseSensitive: false,
    ).firstMatch(header);
    name ??= ordinary?.group(1) ?? ordinary?.group(2);
    final safe = name?.trim();
    if (safe == null ||
        safe.length > 180 ||
        !safe.toLowerCase().endsWith('.pdf') ||
        safe.contains(RegExp('[\\\\/\\x00-\\x1f\\x7f]'))) {
      return fallback;
    }
    return safe;
  }
}

final exportApiProvider = Provider<ExportApi>(
  (ref) => ExportApi(ref.watch(apiClientProvider).dio),
);
