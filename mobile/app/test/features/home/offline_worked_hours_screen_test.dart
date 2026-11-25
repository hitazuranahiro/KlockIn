import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/auth/session.dart';
import 'package:klockin/features/auth/data/auth_models.dart';
import 'package:klockin/features/home/data/confirmed_work_snapshot.dart';
import 'package:klockin/features/home/data/confirmed_work_store.dart';
import 'package:klockin/features/home/data/home_api.dart';
import 'package:klockin/features/home/data/home_models.dart';
import 'package:klockin/features/home/ui/home_screen.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';
import 'package:klockin/features/punch/data/punch_sync.dart';

const _session = Session(
  host: 'https://klockin.example',
  user: SignedInUser(id: 4, fullName: 'Employee'),
  capabilities: Capabilities.empty,
  isCleartext: false,
  geoFencingEnabled: false,
  faceDetectionEnabled: false,
);

class _ActiveSession extends SessionController {
  @override
  Session? build() => _session;
}

const _today = {
  'worked': '03:12:40',
  'workday': '2026-11-25',
  'time_zone': 'Asia/Manila',
  'confirmed_at': '2026-11-25T23:55:00+08:00',
  'workday_starts_at': '2026-11-25T00:00:00+08:00',
  'workday_ends_at': '2026-11-26T00:00:00+08:00',
};

Widget _home({
  required Future<HomeData> Function() loadHome,
  required Stream<bool> connectivity,
  required DateTime Function() clock,
}) => ProviderScope(
  overrides: [
    sessionProvider.overrideWith(_ActiveSession.new),
    homeProvider.overrideWith((ref) => loadHome()),
    punchConnectivityProvider.overrideWith((ref) => connectivity),
    recentPunchesProvider.overrideWith((ref) async => []),
    pendingPunchCountProvider.overrideWith((ref) async => 0),
    confirmedWorkProvider(
      punchQueueAccount(_session),
    ).overrideWith((ref) async => ConfirmedWorkSnapshot.fromJson(_today)),
    homeClockProvider.overrideWithValue(clock),
  ],
  child: const MaterialApp(home: HomeScreen()),
);

void main() {
  testWidgets(
    'cold offline Home freezes the cached total and hides it at expiry',
    (tester) async {
      final snapshot = ConfirmedWorkSnapshot.fromJson(_today)!;
      var now = DateTime.utc(2026, 11, 25, 15, 59, 50);
      final network = Completer<HomeData>();
      await tester.pumpWidget(
        _home(
          loadHome: () => network.future,
          connectivity: Stream.value(false),
          clock: () => now,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Last confirmed worked hours'), findsOneWidget);
      expect(find.text('03:12:40'), findsOneWidget);
      expect(find.text('Workday 2026-11-25'), findsOneWidget);
      expect(
        find.text('As of 25 Nov 2026, 23:55 · Asia/Manila'),
        findsOneWidget,
      );
      expect(find.text('Worked today'), findsNothing);
      expect(
        find.text('Connect to the internet to start or end a break.'),
        findsOneWidget,
      );
      expect(find.text('Start break'), findsNothing);
      expect(find.text('End break'), findsNothing);

      now = now.add(const Duration(seconds: 5));
      await tester.pump(const Duration(seconds: 5));
      expect(find.text('03:12:40'), findsOneWidget);

      now = snapshot.workdayEndsAt;
      await tester.pump(const Duration(seconds: 5));
      expect(find.text('03:12:40'), findsNothing);
      expect(
        find.text('Confirmed worked hours are unavailable for this workday.'),
        findsOneWidget,
      );
    },
  );

  testWidgets('losing connectivity replaces an already-open live ticker', (
    tester,
  ) async {
    final network = StreamController<bool>();
    addTearDown(network.close);
    final online = HomeData.fromJson({
      'employee': {'id': 4, 'full_name': 'Employee'},
      'punch': {'is_clocked_in': true, 'clock_in_time': '20:43'},
      'today': _today,
    });
    network.add(true);
    await tester.pumpWidget(
      _home(
        loadHome: () async => online,
        connectivity: network.stream,
        clock: () => DateTime.utc(2026, 11, 25, 15, 56),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Worked today'), findsOneWidget);

    network.add(false);
    await tester.pumpAndSettle();
    expect(find.text('Worked today'), findsNothing);
    expect(find.text('Last confirmed worked hours'), findsOneWidget);
    expect(find.text('03:12:40'), findsOneWidget);
  });
}
