import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/api_failure.dart';
import 'package:klockin/features/home/data/home_api.dart';
import 'package:klockin/features/home/data/home_models.dart';

const _breakJson = <String, dynamic>{
  'enabled': true,
  'can_start': false,
  'allowed_seconds': 3600,
  'used_seconds': 60,
  'remaining_seconds': 3540,
  'active_since': '2026-11-26T13:00:00+08:00',
  'as_of': '2026-11-26T13:01:00+08:00',
};

void main() {
  test('Home can read server break policy and tolerate older servers', () {
    final policy = HomeData.fromJson({'break_policy': _breakJson}).breakPolicy!;
    expect(policy.enabled, isTrue);
    expect(policy.canStart, isFalse);
    expect(policy.allowedSeconds, 3600);
    expect(policy.usedSeconds, 60);
    expect(policy.remainingSeconds, 3540);
    expect(policy.activeSince, DateTime.utc(2026, 11, 26, 5));
    expect(policy.asOf, DateTime.utc(2026, 11, 26, 5, 1));
    expect(HomeData.fromJson({}).breakPolicy, isNull);
  });

  test('break actions send JSON to the versioned mobile endpoint', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://example.com/api/v1'));
    addTearDown(dio.close);
    final actions = <String>[];
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          expect(options.method, 'POST');
          expect(options.uri.path, '/api/v1/mobile/break/');
          final action = (options.data as Map<String, dynamic>)['action'];
          actions.add(action as String);
          handler.resolve(
            Response<dynamic>(
              requestOptions: options,
              data: action == 'start'
                  ? _breakJson
                  : {..._breakJson, 'active_since': null, 'can_start': true},
            ),
          );
        },
      ),
    );
    final api = HomeApi(dio);
    expect((await api.changeBreak(BreakAction.start)).isActive, isTrue);
    expect((await api.changeBreak(BreakAction.end)).isActive, isFalse);
    expect(actions, ['start', 'end']);
  });

  test('malformed break action responses are incompatible', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://example.com/api/v1'));
    addTearDown(dio.close);
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          handler.resolve(Response<dynamic>(requestOptions: options, data: {}));
        },
      ),
    );
    await expectLater(
      HomeApi(dio).changeBreak(BreakAction.start),
      throwsA(isA<ApiIncompatibleServer>()),
    );
  });
}
