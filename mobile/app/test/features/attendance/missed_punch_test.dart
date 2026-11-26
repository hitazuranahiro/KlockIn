import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:klockin/features/approvals/data/approval_models.dart';
import 'package:klockin/features/approvals/data/approvals_api.dart';
import 'package:klockin/features/attendance/data/attendance_api.dart';
import 'package:klockin/features/attendance/data/missed_punch_models.dart';
import 'package:klockin/features/attendance/ui/missed_punch_screen.dart';
import 'package:klockin/features/requests/data/request_models.dart';
import 'package:klockin/features/requests/data/requests_api.dart';

Map<String, dynamic> _result({
  int id = 71,
  int employeeId = 14,
  String status = 'pending',
  String? timeIn,
  String? timeOut = '18:06:00',
}) => {
  'id': id,
  'employee_id': employeeId,
  'employee_first_name': 'Amara',
  'employee_last_name': 'Cruz',
  'attendance_date': '2026-09-30',
  'time_in': timeIn,
  'time_out': timeOut,
  'reason': 'Forgot at the end of the shift',
  'status': status,
  'requested_at': '2026-10-01T12:00:00Z',
};

Dio _client(Object? Function(RequestOptions) respond) => Dio()
  ..interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) {
        handler.resolve(
          Response<Object?>(requestOptions: options, data: respond(options)),
        );
      },
    ),
  );

void main() {
  test('each supplied side is sent without the other', () {
    final day = DateTime(2026, 9, 30);
    expect(
      MissedPunchDraft(
        attendanceDate: day,
        reason: '  Forgot  ',
        timeIn: '09:30',
      ).toJson(),
      {'attendance_date': '2026-09-30', 'time_in': '09:30', 'reason': 'Forgot'},
    );
    expect(
      MissedPunchDraft(
        attendanceDate: day,
        reason: 'Forgot',
        timeOut: '18:06',
      ).toJson(),
      {
        'attendance_date': '2026-09-30',
        'time_out': '18:06',
        'reason': 'Forgot',
      },
    );
  });

  test('both sides can be sent with an explicit next-day checkout', () {
    expect(
      MissedPunchDraft(
        attendanceDate: DateTime(2026, 9, 30),
        reason: 'Forgot',
        timeIn: '22:00',
        timeOut: '06:30',
        checkoutNextDay: true,
      ).toJson(),
      {
        'attendance_date': '2026-09-30',
        'time_in': '22:00',
        'time_out': '06:30',
        'clock_out_date': '2026-10-01',
        'reason': 'Forgot',
      },
    );
  });

  test(
    'employee history loads additional pages and shows exact request states',
    () async {
      final dio = _client((request) {
        if (request.path != missedPunchPath) return <Object>[];
        expect(request.queryParameters.containsKey('scope'), isFalse);
        return switch (request.queryParameters['page']) {
          1 => {
            'next': '$missedPunchPath?page=2',
            'results': [_result(), _result(id: 72, status: 'approved')],
          },
          2 => {
            'next': null,
            'results': [
              _result(
                id: 73,
                status: 'rejected',
                timeIn: '09:00:00',
                timeOut: null,
              ),
            ],
          },
          final page => throw StateError('Unexpected history page $page'),
        };
      });
      final inbox = await RequestsApi(dio).fetchInbox();
      final byId = {for (final item in inbox.requests) item.id: item};
      expect(byId[71]?.state, RequestState.pending);
      expect(byId[72]?.state, RequestState.approved);
      expect(byId[73]?.state, RequestState.rejected);
      expect(byId[71]?.detail, 'Clock-out 18:06');
      expect(byId[73]?.detail, 'Clock-in 09:00');
    },
  );

  test(
    'superior reads pending reports and can approve or reject them',
    () async {
      final writes = <String>[];
      final dio = _client((request) {
        if (request.method == 'PUT') {
          writes.add(request.path);
          return _result();
        }
        if (request.path != missedPunchPath) return <Object>[];
        expect(request.queryParameters['scope'], 'approvals');
        return {
          'next': null,
          'results': [
            _result(),
            _result(id: 72, status: 'approved'),
            _result(id: 73, employeeId: 1),
          ],
        };
      });
      final api = ApprovalsApi(dio);
      final item = (await api.fetchInbox(selfId: 1)).items.single;
      expect(item.kind, ApprovalKind.missedPunch);
      expect(item.name, 'Amara Cruz');
      expect(item.ask, '30 Sep · Clock-out 18:06');
      expect(item.reason, 'Forgot at the end of the shift');
      expect(item.canReject, isTrue);
      await api.decide(item, approve: true);
      await api.decide(item, approve: false);
      expect(writes, [
        '${missedPunchPath}71/approve/',
        '${missedPunchPath}71/reject/',
      ]);
    },
  );

  testWidgets('employee form submits a checkout-only request', (tester) async {
    final writes = <RequestOptions>[];
    final api = AttendanceApi(
      _client((request) {
        writes.add(request);
        return _result();
      }),
    );
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, _) => Scaffold(
            body: TextButton(
              onPressed: () => context.push('/missed'),
              child: const Text('Open form'),
            ),
          ),
        ),
        GoRoute(path: '/missed', builder: (_, _) => const MissedPunchScreen()),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [attendanceApiProvider.overrideWithValue(api)],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.tap(find.text('Open form'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Clock-out'));
    await tester.pumpAndSettle();
    expect(find.text('Clock-in time'), findsNothing);
    expect(find.text('Clock-out time'), findsOneWidget);
    await tester.enterText(find.byType(TextField).first, '18:06');
    await tester.enterText(find.byType(TextField).last, 'Forgot at checkout');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit request'));
    await tester.pumpAndSettle();

    expect(writes.single.method, 'POST');
    expect(writes.single.path, missedPunchPath);
    final body = writes.single.data as Map<String, dynamic>;
    expect(body['time_out'], '18:06');
    expect(body.containsKey('time_in'), isFalse);
    expect(body['reason'], 'Forgot at checkout');
    expect(find.text('Open form'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
