// Modified for KlockIN by Tomeku, 2026-11-25.
/// Home screen behaviour.
///
/// States matter more than pixels here: a first load shows skeletons rather
/// than a spinner, optional sections disappear when empty rather than leaving
/// a hole, and a failure is recoverable rather than a dead end.
library;

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:klockin/core/api/api_failure.dart';
import 'package:klockin/core/theme/app_theme.dart';
import 'package:klockin/features/auth/data/auth_models.dart';
import 'package:klockin/features/home/data/home_api.dart';
import 'package:klockin/features/home/data/home_models.dart';
import 'package:klockin/features/home/ui/home_screen.dart';
import 'package:klockin/l10n/app_localizations.dart';
import 'package:klockin/shared/widgets/app_button.dart';
import 'package:klockin/shared/widgets/app_card.dart';

HomeData sample({
  String role = 'employee',
  bool clockedIn = true,
  int unread = 0,
  List<ColleagueOnLeave> onLeave = const [],
  AnnouncementSummary? announcement,
  bool geofence = true,
  BreakPolicy? breakPolicy,
}) {
  return HomeData(
    user: const SignedInUser(id: 1, fullName: 'Nisha Prakash'),
    capabilities: Capabilities(
      role: role,
      permissions: const {'view_team': true},
      features: const {'leave': true},
    ),
    punch: PunchState(isClockedIn: clockedIn, clockInTime: '09:04'),
    geofence: GeofenceState(enabled: geofence),
    today: const TodayTotals(
      worked: '03:12:40',
      breakTime: '00:30:00',
      overtime: '00:45:00',
    ),
    onLeaveToday: onLeave,
    unreadNotifications: unread,
    announcement: announcement,
    breakPolicy: breakPolicy,
  );
}

/// Renders at the size the design was drawn for.
///
/// The default 800x600 test surface is not a phone, and laying a phone screen
/// out in a landscape desktop window produces overflow warnings that say
/// nothing about the real product.
Future<void> pumpHome(
  WidgetTester tester, {
  required Future<HomeData> Function() load,
  DateTime Function()? clock,
  HomeApi? breakApi,
  Size logicalSize = const Size(402, 874),
}) async {
  tester.view.physicalSize = logicalSize * 3;
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);

  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
      GoRoute(path: '/punch', builder: (_, _) => const SizedBox()),
      GoRoute(path: '/time', builder: (_, _) => const SizedBox()),
      GoRoute(path: '/team', builder: (_, _) => const SizedBox()),
      GoRoute(path: '/requests', builder: (_, _) => const SizedBox()),
      GoRoute(path: '/me', builder: (_, _) => const SizedBox()),
    ],
  );

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        homeProvider.overrideWith((ref) => load()),
        if (breakApi != null) homeApiProvider.overrideWithValue(breakApi),
        if (clock != null) homeClockProvider.overrideWithValue(clock),
      ],
      child: MaterialApp.router(
        theme: buildAppTheme(),
        localizationsDelegates: const [
          AppL10n.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppL10n.supportedLocales,
        routerConfig: router,
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

BreakPolicy _policy(DateTime now, {int used = 0, DateTime? activeSince}) {
  return BreakPolicy(
    enabled: true,
    canStart: activeSince == null && used < 10,
    allowedSeconds: 10,
    usedSeconds: used,
    remainingSeconds: used >= 10 ? 0 : 10 - used,
    activeSince: activeSince,
    asOf: now,
    receivedAt: now,
  );
}

class _BreakApi extends HomeApi {
  _BreakApi(this.change) : super(Dio());

  final Future<BreakPolicy> Function(BreakAction) change;

  @override
  Future<BreakPolicy> changeBreak(BreakAction action) => change(action);
}

void main() {
  testWidgets('a first load shows skeletons, not a spinner', (tester) async {
    // The handoff is explicit: skeletons matching each card's geometry, never
    // a spinner over the whole screen.
    //
    // A Completer rather than Future.delayed, so the pending load does not
    // leave a live timer behind when the test tree is torn down.
    final pending = Completer<HomeData>();
    addTearDown(() => pending.complete(sample()));

    await pumpHome(tester, load: () => pending.future);

    expect(find.byType(AppCard), findsWidgets);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('renders local clock, shift activity and name', (tester) async {
    await pumpHome(
      tester,
      load: () async => sample(),
      clock: () => DateTime(2026, 11, 25, 13, 55),
    );

    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Nisha Prakash'), findsOneWidget);
    expect(find.text('13:55'), findsOneWidget);
    expect(find.text('On the clock'), findsOneWidget);
    expect(find.text('Worked today'), findsOneWidget);
    expect(find.text('03:12:40'), findsOneWidget);
    expect(find.text('First clock-in'), findsOneWidget);
    expect(find.text('09:04'), findsOneWidget);
    expect(find.text('Break 30m'), findsOneWidget);
    expect(find.textContaining('left in shift'), findsNothing);
  });

  testWidgets('clocked in offers Clock out', (tester) async {
    await pumpHome(tester, load: () async => sample());
    expect(find.text('Clock out'), findsOneWidget);
  });

  testWidgets('starts and ends a break with server-confirmed allowance', (
    tester,
  ) async {
    var now = DateTime.utc(2026, 11, 26, 5);
    var home = sample(breakPolicy: _policy(now));
    final started = Completer<BreakPolicy>();
    final actions = <BreakAction>[];
    await pumpHome(
      tester,
      load: () async => home,
      clock: () => now,
      logicalSize: const Size(402, 1100),
      breakApi: _BreakApi((action) async {
        actions.add(action);
        if (action == BreakAction.start) return started.future;
        final result = _policy(now, used: 13);
        home = sample(breakPolicy: result);
        return result;
      }),
    );

    expect(find.text('Allowed'), findsOneWidget);
    expect(find.text('Used'), findsOneWidget);
    expect(find.text('Remaining'), findsOneWidget);
    expect(find.text('Total breaks 30m'), findsOneWidget);
    expect(find.text('Clock out'), findsOneWidget);
    await tester.tap(find.text('Start break'));
    await tester.pump();
    final saving = tester.widget<AppButton>(
      find.widgetWithText(AppButton, 'Saving break…'),
    );
    expect(saving.onPressed, isNull);

    now = now.add(const Duration(seconds: 1));
    started.complete(_policy(now, activeSince: now));
    await tester.pumpAndSettle();
    expect(find.text('On break'), findsOneWidget);
    expect(find.text('End break'), findsOneWidget);

    now = now.add(const Duration(seconds: 13));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('00:00:13'), findsOneWidget);
    expect(find.text('00:00:00'), findsOneWidget);
    expect(find.text('03:12:40'), findsOneWidget);
    expect(find.text('Clock out'), findsOneWidget);

    await tester.tap(find.text('End break'));
    await tester.pumpAndSettle();
    expect(actions, [BreakAction.start, BreakAction.end]);
    expect(find.text('On the clock'), findsOneWidget);
    expect(find.text('You’ve used your break allowance.'), findsOneWidget);
    final exhausted = tester.widget<AppButton>(
      find.widgetWithText(AppButton, 'Start break'),
    );
    expect(exhausted.onPressed, isNull);
  });

  testWidgets('reconciles a rejected start with a break from the web', (
    tester,
  ) async {
    final now = DateTime.utc(2026, 11, 26, 5);
    var home = sample(breakPolicy: _policy(now));
    await pumpHome(
      tester,
      load: () async => home,
      clock: () => now,
      logicalSize: const Size(402, 1100),
      breakApi: _BreakApi((action) async {
        home = sample(breakPolicy: _policy(now, activeSince: now));
        throw const ApiUnknown('A break is already in progress.');
      }),
    );

    await tester.tap(find.text('Start break'));
    await tester.pumpAndSettle();
    expect(find.text('A break is already in progress.'), findsOneWidget);
    expect(find.text('End break'), findsOneWidget);
  });

  testWidgets(
    'refreshes a break started on another device while Home is open',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final now = DateTime.utc(2026, 11, 26, 5);
      var home = sample(breakPolicy: _policy(now));
      await pumpHome(
        tester,
        load: () async => home,
        clock: () => now,
        logicalSize: const Size(402, 1100),
      );
      expect(find.text('Start break'), findsOneWidget);

      home = sample(breakPolicy: _policy(now, activeSince: now));
      await tester.pump(const Duration(seconds: 45));
      await tester.pumpAndSettle();
      expect(find.text('End break'), findsOneWidget);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      home = sample(clockedIn: false, breakPolicy: _policy(now, used: 3));
      await tester.pump(const Duration(seconds: 45));
      expect(find.text('End break'), findsOneWidget);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.text('Clock in'), findsOneWidget);
      expect(find.text('End break'), findsNothing);
      expect(find.text('Start break'), findsNothing);
    },
  );

  testWidgets('punch action remains reachable at large text sizes', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpHome(
      tester,
      load: () async => sample(),
      clock: () => DateTime(2026, 11, 25, 13, 55),
      logicalSize: const Size(320, 640),
    );

    final clockOut = find.widgetWithText(FilledButton, 'Clock out');
    await tester.ensureVisible(clockOut);
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(clockOut.hitTestable(), findsOneWidget);
    expect(find.text('13:55'), findsOneWidget);
  });

  testWidgets('clocked out offers Clock in', (tester) async {
    await pumpHome(tester, load: () async => sample(clockedIn: false));
    expect(find.text('Clock in'), findsOneWidget);
    // Checked in earlier today (the sample has a first-in), now out.
    expect(find.text('Clocked out'), findsOneWidget);
  });

  testWidgets('the worksite location note shows when the feature is on', (
    tester,
  ) async {
    await pumpHome(tester, load: () async => sample());
    expect(find.text('Worksite location required'), findsOneWidget);
  });

  testWidgets('the worksite location note is absent when the feature is off', (
    tester,
  ) async {
    // A pill that says nothing is worse than no pill.
    await pumpHome(tester, load: () async => sample(geofence: false));
    expect(find.text('Worksite location required'), findsNothing);
  });

  testWidgets('a plain employee gets no role band', (tester) async {
    await pumpHome(tester, load: () async => sample());
    expect(find.textContaining('requests to review'), findsNothing);
    expect(find.textContaining('HR desk'), findsNothing);
  });

  testWidgets('no band claims a count the server has not sent', (tester) async {
    // The band used to render "0 requests need you" for every manager: the
    // count was hard-wired. It stays hidden until the home aggregate carries
    // a real pending-approvals number.
    for (final role in ['manager', 'hrexec']) {
      await pumpHome(tester, load: () async => sample(role: role));
      expect(
        find.textContaining('requests to review'),
        findsNothing,
        reason: role,
      );
      expect(find.textContaining('HR desk'), findsNothing, reason: role);
    }
  });

  testWidgets('optional sections are omitted when empty', (tester) async {
    await pumpHome(tester, load: () async => sample());

    expect(find.text('On leave today'), findsNothing);
    expect(find.text('Latest announcement'), findsNothing);
  });

  testWidgets('on-leave and announcement render when present', (tester) async {
    await pumpHome(
      tester,
      load: () async => sample(
        onLeave: const [ColleagueOnLeave(id: 2, name: 'Arun Menon')],
        announcement: const AnnouncementSummary(id: 1, title: 'Q3 opens'),
      ),
    );

    await tester.scrollUntilVisible(find.text('On leave today'), 120);
    expect(find.text('On leave today'), findsOneWidget);
    expect(find.text('Arun Menon'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Q3 opens'), 120);
    expect(find.text('Q3 opens'), findsOneWidget);
  });

  testWidgets('a failure is explained and retryable', (tester) async {
    await pumpHome(
      tester,
      load: () async => throw const ApiNetwork('No connection.'),
    );
    // The rejection resolves a microtask later than the first frame.
    await tester.pump();

    expect(find.text('COULD NOT LOAD'), findsOneWidget);
    expect(find.text('No connection.'), findsOneWidget);
    expect(find.text('Tap to try again'), findsOneWidget);
  });

  testWidgets('with no unread, the bell is announced plainly', (tester) async {
    await pumpHome(tester, load: () async => sample());
    expect(find.bySemanticsLabel('Notifications'), findsOneWidget);
  });

  test('home employee block is read from name and avatar', () {
    final user = SignedInUser.fromJson({
      'id': 4,
      'name': 'Adam Admin',
      'avatar': '/media/adam.png',
    });
    expect(user.fullName, 'Adam Admin');
    expect(user.avatarUrl, '/media/adam.png');
  });

  test('login employee block still uses full_name', () {
    final user = SignedInUser.fromJson({
      'id': 4,
      'full_name': 'Adam Admin',
      'name': 'ignored when login sends both',
      'employee_profile': '/media/adam.png',
    });
    expect(user.fullName, 'Adam Admin');
    expect(user.avatarUrl, '/media/adam.png');
  });

  testWidgets('unread count is announced to screen readers', (tester) async {
    // The dot is the visual signal; the count has to reach anyone not
    // looking at it.
    await pumpHome(tester, load: () async => sample(unread: 7));
    expect(find.bySemanticsLabel('Notifications, 7 unread'), findsOneWidget);
  });
}
