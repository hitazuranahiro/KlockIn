// Modified for KlockIN by Tomeku, 2026-11-25.
/// Pins the actual bug: a completed check-out hold must show success on
/// screen before it navigates away.
///
/// Reported live against hr.demo.horilla.com: the hold-to-confirm completed,
/// the screen popped back to Home in the same frame with nothing but a small
/// toast, and -- reading that as "the hold didn't register" -- holding again
/// got a genuine, correct "already checked out" from the server. The server
/// was right both times; the app gave no way to tell the first punch had
/// already landed. The fix is a visible confirmed state between "hold
/// completed" and "screen changes"; this test is what would have caught its
/// absence.
library;

import 'dart:typed_data';
import 'dart:ui' show SemanticsAction;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:klockin/core/theme/app_theme.dart';
import 'package:klockin/features/home/data/home_models.dart';
import 'package:klockin/features/punch/data/punch_controller.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';
import 'package:klockin/features/punch/data/location_service.dart';
import 'package:klockin/features/punch/ui/punch_location_map.dart';
import 'package:klockin/features/punch/ui/punch_screen.dart';
import 'package:klockin/l10n/app_localizations.dart';
import 'package:klockin/shared/widgets/hold_to_confirm_button.dart';

/// Public API only: PunchController's network call is private to the app's
/// library, so faking it here can't accidentally exercise it.
class _FakePunchController implements PunchController {
  _FakePunchController({this.detectedAddress});

  final String? detectedAddress;
  int submitCalls = 0;

  @override
  Future<PunchPreparation> prepare({
    required bool isClockingIn,
    required GeofenceState geofence,
  }) async => PunchPreparation(
    isClockingIn: isClockingIn,
    coordinates: const Coordinates(latitude: 14, longitude: 121),
  );

  @override
  Future<PunchReceipt> submit(
    PunchPreparation preparation,
    Uint8List selfie, {
    DateTime? punchedAt,
  }) async {
    submitCalls++;
    // A second call is exactly the server behaviour this bug produced: the
    // real endpoint has no queue, so calling it twice for one hold is the
    // "already checked out" failure, not a success.
    if (submitCalls > 1) {
      throw StateError('submit() called again after it already succeeded');
    }
    return PunchReceipt(
      PunchSyncState.synced,
      detectedAddress: detectedAddress,
    );
  }
}

const _locationPreview = MethodChannel('com.tomeku.klockin/location-preview');

Future<void> _pumpPunch(
  WidgetTester tester,
  _FakePunchController fake, {
  TargetPlatform platform = TargetPlatform.android,
  Future<Object?> Function(MethodCall)? previewHandler,
}) async {
  debugDefaultTargetPlatformOverride = platform;
  addTearDown(() => debugDefaultTargetPlatformOverride = null);
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(
    _locationPreview,
    previewHandler ?? (_) async => null,
  );
  addTearDown(() => messenger.setMockMethodCallHandler(_locationPreview, null));
  tester.view.physicalSize = const Size(390 * 3, 844 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);

  // '/home' is the initial location and '/punch' is reached by pushing --
  // matching how the real app opens it, and giving context.pop() something
  // underneath it to return to. Declaring '/punch' as a second top-level
  // location with no page pushed above it is what "There is nothing to pop"
  // was reporting.
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (_, _) => const Text('HOME')),
      GoRoute(
        path: '/punch',
        builder: (_, _) => PunchScreen(
          isClockingIn: false,
          geofence: const GeofenceState(enabled: false),
          captureSelfie: (_) async => Uint8List(1),
          today: const TodayTotals(
            worked: '06:42:02',
            breakTime: '00:32:00',
            overtime: '00:00:00',
          ),
          clockInTime: '09:02',
        ),
      ),
    ],
  );

  await tester.pumpWidget(
    ProviderScope(
      overrides: [punchControllerProvider.overrideWithValue(fake)],
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

  router.push('/punch');
  await tester.pump();
  // Let the initial location read resolve before pressing the hold control.
  await tester.pump(const Duration(milliseconds: 50));
  // The method-channel result schedules its own frame after the location read.
  await tester.pump();
}

/// Advances the fake clock in small steps.
///
/// A single large `pump(duration)` does not reliably carry an
/// [AnimationController] driven by a real gesture callback across its
/// completion boundary in this binding -- confirmed by isolating
/// [HoldToConfirmButton] alone: identical large jumps silently stalled
/// partway, while the same total time in small steps ticked and completed
/// every time. Small steps are the reliable way to test it.
Future<void> pumpTicks(
  WidgetTester tester,
  Duration total, {
  Duration step = const Duration(milliseconds: 50),
}) async {
  var remaining = total;
  while (remaining > Duration.zero) {
    final tick = remaining < step ? remaining : step;
    await tester.pump(tick);
    remaining -= tick;
  }
}

void main() {
  testWidgets(
    'a completed check-out shows a confirmed state before the screen changes',
    (tester) async {
      final semantics = tester.ensureSemantics();
      final fake = _FakePunchController();
      try {
        await _pumpPunch(tester, fake);

        // A sighted press must not be a tap action. On the phone that action
        // fired as soon as the finger went down, clocking out before the bar
        // finished, and the bar's own confirm then got "Already clocked-out".
        final node = tester.getSemantics(find.byType(HoldToConfirmButton));
        expect(node.getSemanticsData().hasAction(SemanticsAction.tap), isFalse);

        // Press and hold: completion is time-based on the animation, not on
        // the gesture ending, so advancing past holdFor is the hold.
        final gesture = await tester.startGesture(
          tester.getCenter(find.byType(HoldToConfirmButton)),
        );
        // Margin beyond holdFor: the first pumped tick only resolves the tap
        // recognizer's arena and registers the gesture down -- it contributes
        // no animation progress of its own -- so the animation's own clock
        // starts slightly after this loop's clock does.
        await pumpTicks(tester, const Duration(milliseconds: 1300));

        // The moment the hold completes, before the screen has changed:
        // exactly one submit, and something on screen unambiguously says so.
        expect(fake.submitCalls, 1);
        expect(find.text('Clocked out'), findsOneWidget);

        // The hold control itself is gone -- there is nothing left to press
        // that could trigger a second, now-invalid, check-out.
        expect(find.byType(HoldToConfirmButton), findsNothing);

        await gesture.up();
        await pumpTicks(tester, const Duration(milliseconds: 950));
        final map = tester.widget<PunchLocationMap>(
          find.byType(PunchLocationMap),
        );
        expect(map.latitude, 14);
        expect(map.longitude, 121);
        expect(find.text('HOME'), findsNothing);
        await tester.tap(find.text('Done'));
        await pumpTicks(tester, const Duration(milliseconds: 400));
        expect(find.text('HOME'), findsOneWidget);

        // No further submit happened on the way out.
        expect(fake.submitCalls, 1);
      } finally {
        semantics.dispose();
      }
    },
  );

  testWidgets(
    'map links fit at 390 points and open only on tap below the receipt address',
    (tester) async {
      const address = '12 Ayala Avenue, Makati, Metro Manila';
      const previewAddress = 'Nearby Street, Municipality';
      final calls = <MethodCall>[];
      final fake = _FakePunchController(detectedAddress: address);
      await _pumpPunch(
        tester,
        fake,
        previewHandler: (call) async {
          calls.add(call);
          return switch (call.method) {
            'lookupCapturedAddress' => {'address': previewAddress},
            'openGoogleMaps' => true,
            _ => null,
          };
        },
      );
      expect(find.text(previewAddress), findsOneWidget);

      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(HoldToConfirmButton)),
      );
      await pumpTicks(tester, const Duration(milliseconds: 1300));
      await gesture.up();
      await pumpTicks(tester, const Duration(seconds: 1));

      expect(find.text('Detected address'), findsOneWidget);
      expect(find.text(address), findsOneWidget);
      expect(find.text(previewAddress), findsNothing);
      expect(find.text('HOME'), findsNothing);
      expect(calls.map((call) => call.method), ['lookupCapturedAddress']);

      final maps = find.text('Open in Google Maps');
      final streetView = find.text('Street View');
      final addressBottom = tester.getBottomLeft(find.text(address)).dy;
      for (final action in [maps, streetView]) {
        final bounds = tester.getRect(action);
        expect(bounds.top, greaterThan(addressBottom));
        expect(bounds.left, greaterThanOrEqualTo(0));
        expect(bounds.right, lessThanOrEqualTo(390));
      }
      expect(tester.takeException(), isNull);
      await tester.tap(maps);
      await tester.pump();
      expect(calls.map((call) => call.method), [
        'lookupCapturedAddress',
        'openGoogleMaps',
      ]);
      final url = Uri.parse((calls.last.arguments as Map)['url'] as String);
      expect(url.origin, 'https://www.google.com');
      expect(url.queryParameters, {'api': '1', 'query': '14.0,121.0'});

      await tester.tap(streetView);
      await tester.pump();
      expect(calls.map((call) => call.method), [
        'lookupCapturedAddress',
        'openGoogleMaps',
        'openGoogleMaps',
      ]);
      final streetViewUrl = Uri.parse(
        (calls.last.arguments as Map)['url'] as String,
      );
      expect(streetViewUrl.origin, 'https://www.google.com');
      expect(streetViewUrl.path, '/maps/@');
      expect(streetViewUrl.queryParameters, {
        'api': '1',
        'map_action': 'pano',
        'viewpoint': '14.0,121.0',
      });

      await tester.tap(find.text('Done'));
      await pumpTicks(tester, const Duration(milliseconds: 400));
      expect(find.text('HOME'), findsOneWidget);
    },
  );

  testWidgets(
    'iOS falls back to captured coordinates without the paired Apple map',
    (tester) async {
      const previewAddress = 'Apple Maps address without a map';
      await _pumpPunch(
        tester,
        _FakePunchController(),
        platform: TargetPlatform.iOS,
        previewHandler: (_) async => {'address': previewAddress},
      );

      expect(find.text(previewAddress), findsNothing);
      expect(find.text('14.000000, 121.000000'), findsOneWidget);
      expect(find.byType(HoldToConfirmButton), findsOneWidget);
    },
  );
}
