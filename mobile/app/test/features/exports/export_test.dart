import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/api_failure.dart';
import 'package:klockin/features/exports/data/export_api.dart';
import 'package:klockin/features/exports/data/export_models.dart';
import 'package:klockin/features/exports/ui/export_preview_screen.dart';
import 'package:klockin/features/exports/ui/export_screen.dart';
import 'package:klockin/shared/widgets/app_button.dart';
import 'package:klockin/shared/widgets/app_top_bar.dart';

final _pdf = Uint8List.fromList('%PDF-1.7\nfixture\n%%EOF\n'.codeUnits);

Map<String, Object> _preferences([Map<String, dynamic> payslip = const {}]) => {
  'payslip': {
    'template': 'detailed',
    'show_company': true,
    'show_notes': true,
    'note': 'Original note',
    ...payslip,
  },
  'dtr': {
    'layout': 'am-pm',
    'orientation': 'portrait',
    'show_company': true,
    'show_notes': true,
    'note': '',
    'show_undertime': true,
  },
};

Dio _client(Response<dynamic> Function(RequestOptions) respond) =>
    Dio()
      ..interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) {
            handler.resolve(respond(request));
          },
        ),
      );

class _PdfTools extends ExportPdfTools {
  ExportPdfDocument? rendered;
  ExportPdfDocument? downloaded;
  ExportPdfDocument? shared;

  @override
  Widget preview(ExportPdfDocument document) {
    rendered = document;
    return const Center(child: Text('Rendered server PDF'));
  }

  @override
  Future<bool> download(ExportPdfDocument document) async {
    downloaded = document;
    return true;
  }

  @override
  Future<void> share(ExportPdfDocument document, Rect? bounds) async {
    shared = document;
  }
}

void main() {
  test('DTR sends only display options and the selected month', () async {
    final api = ExportApi(
      _client((request) {
        expect(request.method, 'GET');
        expect(request.path, '/mobile/dtr/');
        expect(request.headers['Accept'], 'application/pdf');
        expect(request.responseType, ResponseType.bytes);
        expect(request.queryParameters, {
          'layout': 'first-last',
          'month': '2026-02',
          'orientation': 'landscape',
          'show_company': '0',
          'show_notes': '1',
          'show_undertime': '0',
          'preview': '1',
        });
        return Response<Uint8List>(
          requestOptions: request,
          data: _pdf,
          headers: Headers.fromMap({
            'content-disposition': [
              "inline; filename*=UTF-8''February%20DTR.pdf",
            ],
          }),
        );
      }),
    );
    final pdf = await api.fetchPdf(
      ExportTarget.dtr(period: DateTime(2026, 2)),
      const ExportSettings(
        layout: 'first-last',
        orientation: 'landscape',
        showCompany: false,
        showUndertime: false,
        note: 'Never include this note in the URL.',
      ),
    );
    expect(pdf.bytes, same(_pdf));
    expect(pdf.filename, 'February DTR.pdf');
  });

  test(
    'a login page or other non-PDF response cannot open as an export',
    () async {
      final api = ExportApi(
        _client(
          (request) => Response<List<int>>(
            requestOptions: request,
            data: '<html>Login</html>'.codeUnits,
          ),
        ),
      );
      await expectLater(
        api.fetchPdf(
          ExportTarget.payslip(id: 21, period: DateTime(2026, 9)),
          const ExportSettings(layout: 'detailed'),
        ),
        throwsA(isA<ApiFailure>()),
      );
    },
  );

  testWidgets('a root PDF preview keeps its only route visible', (
    tester,
  ) async {
    final tools = _PdfTools();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [exportPdfToolsProvider.overrideWithValue(tools)],
        child: MaterialApp(
          home: ExportPreviewScreen(
            target: ExportTarget.dtr(period: DateTime(2026, 11)),
            document: ExportPdfDocument(bytes: _pdf, filename: 'DTR.pdf'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final preview = find.byType(ExportPreviewScreen);
    expect(find.text('DTR preview'), findsOneWidget);
    expect(find.byType(CircleBackButton), findsNothing);
    expect(await Navigator.maybePop(tester.element(preview)), isFalse);
    await tester.pumpAndSettle();
    expect(find.text('Rendered server PDF'), findsOneWidget);
  });

  testWidgets('DTR Back returns to export settings and then to Timekeeping', (
    tester,
  ) async {
    final api = ExportApi(
      _client(
        (request) => Response<dynamic>(
          requestOptions: request,
          data: request.path == ExportApi.preferencesPath
              ? _preferences()
              : _pdf,
        ),
      ),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          exportApiProvider.overrideWithValue(api),
          exportPdfToolsProvider.overrideWithValue(_PdfTools()),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => openDocumentExport(
                  context,
                  ExportTarget.dtr(period: DateTime(2026, 11)),
                ),
                child: const Text('Timekeeping'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Timekeeping'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Preview PDF'));
    await tester.pumpAndSettle();
    expect(find.text('DTR preview'), findsOneWidget);

    await tester.tap(find.byType(CircleBackButton));
    await tester.pumpAndSettle();
    expect(find.text('DTR PDF'), findsOneWidget);
    expect(find.text('Preview PDF'), findsOneWidget);

    await tester.tap(find.byType(CircleBackButton));
    await tester.pumpAndSettle();
    expect(find.text('Timekeeping'), findsOneWidget);
    expect(find.byType(ExportScreen), findsNothing);
  });

  testWidgets('save a private note, then preview, download and share one PDF', (
    tester,
  ) async {
    final requests = <RequestOptions>[];
    final api = ExportApi(
      _client((request) {
        requests.add(request);
        if (request.method == 'PATCH') {
          final data = request.data as Map<String, dynamic>;
          return Response<dynamic>(
            requestOptions: request,
            data: _preferences(data['payslip'] as Map<String, dynamic>),
          );
        }
        if (request.path == ExportApi.preferencesPath) {
          return Response<dynamic>(
            requestOptions: request,
            data: _preferences(),
          );
        }
        return Response<Uint8List>(
          requestOptions: request,
          data: _pdf,
          headers: Headers.fromMap({
            'content-disposition': ['inline; filename="September payslip.pdf"'],
          }),
        );
      }),
    );
    final tools = _PdfTools();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          exportApiProvider.overrideWithValue(api),
          exportPdfToolsProvider.overrideWithValue(tools),
        ],
        child: MaterialApp(
          home: ExportScreen(
            target: ExportTarget.payslip(id: 31, period: DateTime(2026, 9)),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(CircleBackButton), findsNothing);
    await tester.tap(find.widgetWithText(ChoiceChip, 'Compact'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Private payroll note');
    await tester.pumpAndSettle();

    final preview = find.widgetWithText(AppButton, 'Preview PDF');
    expect(tester.widget<AppButton>(preview).onPressed, isNull);
    await tester.tap(find.text('Save as default'));
    await tester.pumpAndSettle();
    expect(requests[1].method, 'PATCH');
    expect(requests[1].data, {
      'payslip': {
        'template': 'compact',
        'show_company': true,
        'show_notes': true,
        'note': 'Private payroll note',
      },
    });

    await tester.tap(preview);
    await tester.pumpAndSettle();
    expect(requests.last.path, '/payroll/payslip-download/31');
    expect(requests.last.queryParameters['template'], 'compact');
    expect(requests.last.queryParameters['format'], 'pdf');
    expect(requests.last.queryParameters.containsKey('note'), isFalse);
    expect(find.text('Rendered server PDF'), findsOneWidget);
    expect(tools.rendered?.bytes, same(_pdf));
    expect(tools.rendered?.filename, 'September payslip.pdf');

    await tester.tap(find.text('Download'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Share'));
    await tester.pumpAndSettle();
    expect(tools.downloaded, same(tools.rendered));
    expect(tools.shared, same(tools.rendered));
    expect(requests, hasLength(3));
    await tester.pumpWidget(const SizedBox());
  });
}
