import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/api_failure.dart';
import 'package:klockin/core/api/error_interceptor.dart';
import 'package:klockin/features/leave/data/leave_api.dart';

LeaveApi leaveApi({int holidayStatus = 200, int balanceStatus = 200}) {
  final client = Dio()
    ..interceptors.add(
      InterceptorsWrapper(
        onRequest: (request, handler) {
          final (status, rows) = switch (request.path) {
            '/leave/available-leave/' => (
              balanceStatus,
              [
                {
                  'id': 1,
                  'leave_type_id': {'id': 2, 'name': 'Annual leave'},
                  'available_days': 5,
                  'carryforward_days': 1,
                },
              ],
            ),
            '/leave/user-request/' => (
              200,
              [
                {
                  'id': 3,
                  'leave_type_id': {'id': 2, 'name': 'Annual leave'},
                  'start_date': '2026-11-20',
                  'end_date': '2026-11-20',
                  'status': 'requested',
                },
              ],
            ),
            '/leave/holiday/' => (
              holidayStatus,
              [
                {
                  'id': 4,
                  'name': 'Company holiday',
                  'start_date': '${DateTime.now().year + 1}-12-25',
                },
              ],
            ),
            _ => throw StateError('Unexpected leave route: ${request.path}'),
          };
          final response = Response<dynamic>(
            requestOptions: request,
            statusCode: status,
            data: {'results': rows},
          );
          if (status == 200) {
            handler.resolve(response);
          } else {
            handler.reject(
              DioException.badResponse(
                statusCode: status,
                requestOptions: request,
                response: response,
              ),
              true,
            );
          }
        },
      ),
    )
    ..interceptors.add(ErrorInterceptor());
  return LeaveApi(client);
}

void main() {
  test(
    'restricted holidays leave the employee balances and requests visible',
    () async {
      final overview = await leaveApi(holidayStatus: 403).fetchOverview();

      expect(overview.balances.single.totalDays, 6);
      expect(overview.requests.single.id, 3);
      expect(overview.holidays, isEmpty);
    },
  );

  test('authorized employees still receive upcoming holidays', () async {
    final overview = await leaveApi().fetchOverview();

    expect(overview.holidays.single.name, 'Company holiday');
  });

  test('a forbidden balance request still reports an access failure', () async {
    await expectLater(
      leaveApi(balanceStatus: 403).fetchOverview(),
      throwsA(isA<ApiForbidden>()),
    );
  });
}
