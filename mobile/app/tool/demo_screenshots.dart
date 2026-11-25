// Modified for KlockIN by Tomeku, 2026-11-25.
/// Captures KlockIN screens from a test account on a KlockIN server.
/// The default output path is ../docs/screenshots/server/. Set
/// KLOCKIN_SCREENSHOT_DIR to write elsewhere.
///
///     KLOCKIN_SERVER_URL=https://klockin.example \
///     DEMO_USERNAME=... DEMO_PASSWORD=... \
///     flutter test tool/demo_screenshots.dart
///
/// Credentials come from the environment. The tool signs in and reads
/// data without submitting punches, leave requests, or approvals.
///
/// Two containers, deliberately. The first signs in and fetches everything
/// a shot needs, for real, inside `runAsync` (the real event loop -- a
/// widget's own `ref.watch` instead starts its fetch on flutter_test's fake
/// clock, whose real socket I/O then never gets a turn to complete). The
/// second is what `KlockInApp` actually mounts onto, with those results
/// (and the session itself) fixed as overrides -- exactly
/// tool/readme_screenshots.dart's pattern, with real answers standing in
/// for the hand-written ones. A widget rebuilding mid-shot then just finds
/// already-resolved state, never a live request racing the fake clock.
library;

import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:klockin/app.dart';
import 'package:klockin/core/auth/session.dart';
import 'package:klockin/core/auth/session_lock.dart';
import 'package:klockin/core/auth/token_store.dart';
import 'package:klockin/features/announcements/data/announcement_models.dart';
import 'package:klockin/features/announcements/data/announcements_api.dart';
import 'package:klockin/features/approvals/data/approval_models.dart';
import 'package:klockin/features/approvals/data/approvals_controller.dart';
import 'package:klockin/features/attendance/data/attendance_api.dart';
import 'package:klockin/features/attendance/data/attendance_models.dart';
import 'package:klockin/features/home/data/home_api.dart';
import 'package:klockin/features/home/data/home_models.dart';
import 'package:klockin/features/leave/data/leave_api.dart';
import 'package:klockin/features/leave/data/leave_models.dart';
import 'package:klockin/features/notifications/data/notification_models.dart';
import 'package:klockin/features/notifications/data/notifications_api.dart';
import 'package:klockin/features/punch/data/punch_sync.dart';
import 'package:klockin/features/team/data/team_api.dart';
import 'package:klockin/features/team/data/team_models.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

import 'screenshot_support.dart';

/// The real one talks to the Keychain, unavailable in a headless test and
/// not the point here -- the token just needs to survive for one run.
class _InMemoryTokenStore implements TokenStore {
  StoredSession? _session;

  @override
  Future<StoredSession?> read() async => _session;

  @override
  Future<void> write(StoredSession session) async => _session = session;

  @override
  Future<void> clear() async => _session = null;
}

/// Hands back the session captured at bootstrap, forever. The widget tree
/// never signs in, restores, or refreshes for real.
class _FixedSession extends SessionController {
  _FixedSession(this._session);

  final Session? _session;

  @override
  Session? build() => _session;
}

class _FixedApprovals extends ApprovalsController {
  _FixedApprovals(this._inbox);

  final ApprovalInbox _inbox;

  @override
  Future<ApprovalInbox> build() async => _inbox;
}

const _shots = {
  'home': '/home',
  'attendance': '/time',
  'leave': '/time/leave',
  'leave-apply': '/time/leave/apply',
  'approvals': '/team/approvals',
  'team': '/team',
  'announcements': '/home/announcements',
  'notifications': '/home/notifications',
  'me': '/me',
};

void main() {
  testWidgets('demo screenshots', (tester) async {
    mockScreenshotConnectivity();
    final host = Platform.environment['KLOCKIN_SERVER_URL'];
    final username = Platform.environment['DEMO_USERNAME'];
    final password = Platform.environment['DEMO_PASSWORD'];
    if (host == null || username == null || password == null) {
      fail(
        'Set KLOCKIN_SERVER_URL, DEMO_USERNAME and DEMO_PASSWORD '
        'in the environment. Nothing is written or approved -- this only '
        'signs in and reads.',
      );
    }

    // flutter_test fakes every HttpClient it sees (every request comes back
    // 400) so a widget test can't accidentally hit the network. That is
    // exactly what this script needs to do, on purpose.
    HttpOverrides.global = null;
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    // The real app never calls this explicitly -- flutter_localizations does
    // it as a side effect of mounting MaterialApp, which by bootstrap time
    // hasn't happened yet.
    await initializeDateFormatting('en');
    await tester.runAsync(loadScreenshotFonts);
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    tester.view
      ..physicalSize = const Size(1179, 2556)
      ..devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    // --- bootstrap: sign in and fetch everything, for real -----------------
    final bootstrap = ProviderContainer(
      // No retries: a real failure should surface immediately, not schedule
      // a Timer that outlives this script's own teardown.
      retry: (_, _) => null,
      overrides: [
        tokenStoreProvider.overrideWithValue(_InMemoryTokenStore()),
        sessionLockProvider.overrideWith((ref) => MemorySessionLock()),
      ],
    );
    final results = await tester.runAsync(() async {
      await bootstrap
          .read(sessionProvider.notifier)
          .signIn(rawHost: host, username: username, password: password)
          .timeout(const Duration(seconds: 30));

      final fetched = await Future.wait([
        bootstrap.read(homeProvider.future),
        bootstrap.read(attendanceOverviewProvider.future),
        bootstrap.read(leaveOverviewProvider.future),
        bootstrap.read(approvalsProvider.future),
        bootstrap.read(teamTodayProvider.future),
        bootstrap.read(announcementsProvider.future),
        bootstrap.read(notificationInboxProvider.future),
      ]).timeout(const Duration(seconds: 60));

      final announcements = fetched[5] as List<Announcement>;
      final detail = announcements.isEmpty
          ? null
          : await bootstrap
                .read(announcementProvider(announcements.first.id).future)
                .timeout(const Duration(seconds: 30));

      return (
        session: bootstrap.read(sessionProvider),
        fetched: fetched,
        detail: detail,
      );
    });
    expect(results!.session, isNotNull, reason: 'sign-in failed');
    bootstrap.dispose();

    final home = results.fetched[0] as HomeData;
    final attendance = results.fetched[1] as AttendanceOverview;
    final leave = results.fetched[2] as LeaveOverview;
    final approvals = results.fetched[3] as ApprovalInbox;
    final team = results.fetched[4] as TeamToday;
    final announcements = results.fetched[5] as List<Announcement>;
    final notifications = results.fetched[6] as NotificationInbox;

    // --- display: KlockInApp mounts onto fixed, already-resolved state -----
    final container = ProviderContainer(
      retry: (_, _) => null,
      overrides: [
        sessionProvider.overrideWith(() => _FixedSession(results.session)),
        sessionRestoreProvider.overrideWith((ref) async {}),
        homeProvider.overrideWith((ref) async => home),
        punchConnectionProvider.overrideWithValue(() async => false),
        attendanceOverviewProvider.overrideWith((ref) async => attendance),
        leaveOverviewProvider.overrideWith((ref) async => leave),
        approvalsProvider.overrideWith(() => _FixedApprovals(approvals)),
        teamTodayProvider.overrideWith((ref) async => team),
        announcementsProvider.overrideWith((ref) async => announcements),
        notificationInboxProvider.overrideWith((ref) async => notifications),
        if (results.detail != null)
          announcementProvider.overrideWith((ref, id) async => results.detail!),
      ],
    );
    addTearDown(container.dispose);

    final boundary = GlobalKey();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: RepaintBoundary(key: boundary, child: const KlockInApp()),
      ),
    );
    await tester.pump(const Duration(seconds: 1));

    final outputDirectory =
        Platform.environment['KLOCKIN_SCREENSHOT_DIR'] ??
        '../docs/screenshots/server';
    final out = Directory(outputDirectory)..createSync(recursive: true);
    Future<void> shoot(String name, String path) async {
      GoRouter.of(tester.element(find.byType(Scaffold).first)).go(path);
      // A push within a branch (e.g. home -> home/announcements) animates in
      // over a few frames; one bare pump() catches it mid-transition, or
      // still showing the screen before it. pumpAndSettle isn't safe here --
      // the punch clock's own periodic Timer means it never truly settles.
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      await tester.runAsync(() async {
        for (final e in find.byType(Image).evaluate()) {
          await precacheImage((e.widget as Image).image, e);
        }
      });
      await tester.pump();

      final render =
          boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      await tester.runAsync(() async {
        final image = await render.toImage(pixelRatio: 3);
        final png = await image.toByteData(format: ui.ImageByteFormat.png);
        File(
          '${out.path}/$name.png',
        ).writeAsBytesSync(png!.buffer.asUint8List());
      });
    }

    for (final MapEntry(key: name, value: path) in _shots.entries) {
      await shoot(name, path);
    }
    if (announcements.isNotEmpty) {
      await shoot(
        'announcement',
        '/home/announcements/${announcements.first.id}',
      );
    }
    debugDefaultTargetPlatformOverride = null;
  }, timeout: const Timeout(Duration(minutes: 3)));
}
