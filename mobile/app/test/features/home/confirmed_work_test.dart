import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/auth/session.dart';
import 'package:klockin/features/auth/data/auth_models.dart';
import 'package:klockin/features/home/data/confirmed_work_snapshot.dart';
import 'package:klockin/features/home/data/confirmed_work_store.dart';
import 'package:klockin/features/home/data/home_api.dart';
import 'package:klockin/features/home/data/home_models.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';

const today = <String, dynamic>{
  'worked': '03:12:40',
  'workday': '2026-11-25',
  'time_zone': 'Asia/Manila',
  'confirmed_at': '2026-11-26T01:00:00+08:00',
  'workday_starts_at': '2026-11-25T00:00:00+08:00',
  'workday_ends_at': '2026-11-26T12:00:00+08:00',
};

Session _session(String host, int id) => Session(
  host: host,
  user: SignedInUser(id: id, fullName: 'Employee'),
  capabilities: Capabilities.empty,
  isCleartext: false,
  geoFencingEnabled: false,
  faceDetectionEnabled: false,
);

final _employee = _session('https://klockin.example', 4);

class _ActiveSession extends SessionController {
  @override
  Session? build() => _employee;
}

class _HomeApi extends HomeApi {
  _HomeApi(this.employeeId) : super(Dio());

  final int employeeId;

  @override
  Future<HomeData> fetch() async => HomeData.fromJson({
    'employee': {'id': employeeId},
    'today': today,
  });
}

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('the server workday controls validity across midnight', () {
    final snapshot = ConfirmedWorkSnapshot.fromJson(today)!;
    expect(snapshot.workedSeconds, 11560);
    expect(snapshot.workday, '2026-11-25');
    expect(snapshot.isCurrentAt(DateTime.utc(2026, 11, 25, 17, 30)), isTrue);
    expect(snapshot.isCurrentAt(DateTime.utc(2026, 11, 26, 4)), isFalse);
    expect(snapshot.isCurrentAt(DateTime.utc(2026, 11, 25, 16, 59)), isFalse);
  });

  test(
    'missing or malformed totals and validity metadata produce no cache',
    () {
      for (final field in today.keys) {
        expect(
          ConfirmedWorkSnapshot.fromJson({...today}..remove(field)),
          isNull,
        );
      }
      expect(
        ConfirmedWorkSnapshot.fromJson({...today, 'worked': '03:72:40'}),
        isNull,
      );
      expect(
        ConfirmedWorkSnapshot.fromJson({
          ...today,
          'confirmed_at': '2026-11-25T17:00:00',
        }),
        isNull,
      );
      expect(
        ConfirmedWorkSnapshot.fromJson({
          ...today,
          'worked': '00:00:00',
        })?.workedSeconds,
        0,
      );
    },
  );

  test(
    'native cache survives recreation and keeps only the newest scoped total',
    () async {
      final store = ConfirmedWorkStore();
      final account = punchQueueAccount(_employee);
      final older = ConfirmedWorkSnapshot.fromJson({
        ...today,
        'worked': '02:12:40',
        'confirmed_at': '2026-11-26T00:00:00+08:00',
      })!;
      await Future.wait([
        store.save(account, ConfirmedWorkSnapshot.fromJson(today)!),
        store.save(account, older),
      ]);

      final reopened = ConfirmedWorkStore();
      expect((await reopened.read(account))?.worked, '03:12:40');
      expect(
        await reopened.read(punchQueueAccount(_session(_employee.host, 5))),
        isNull,
      );
      expect(
        await reopened.read(
          punchQueueAccount(
            _session('https://other.example', _employee.user.id),
          ),
        ),
        isNull,
      );
    },
  );

  test(
    'only the signed-in employee response seeds the offline snapshot',
    () async {
      final scope = punchQueueAccount(_employee);
      final store = ConfirmedWorkStore();
      for (final id in [5, 4]) {
        final container = ProviderContainer(
          overrides: [
            sessionProvider.overrideWith(_ActiveSession.new),
            homeApiProvider.overrideWithValue(_HomeApi(id)),
            confirmedWorkStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);
        await container.read(homeProvider.future);
        expect((await store.read(scope))?.worked, id == 4 ? '03:12:40' : null);
      }
    },
  );
}
