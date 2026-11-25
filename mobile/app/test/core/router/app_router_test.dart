// Modified for KlockIN by Tomeku, 2026-11-25.
/// Navigation structure.
///
/// Detail pages keep their tab while standalone flows use the full screen.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/router/app_router.dart';
import 'package:klockin/core/theme/app_theme.dart';
import 'package:klockin/l10n/app_localizations.dart';
import 'package:klockin/core/scope.dart';
import 'package:klockin/features/attendance/ui/attendance_screen.dart';
import 'package:klockin/features/shell/ui/app_shell.dart';
import 'package:klockin/features/shell/ui/workspace_menu.dart';
import 'package:klockin/features/requests/ui/requests_screen.dart';
import 'package:klockin/shared/widgets/app_bottom_nav.dart';

/// Note: pump() rather than pumpAndSettle().
///
/// Skeleton placeholders animate on a repeating controller, which by
/// definition never settles -- pumpAndSettle would hang until it timed out.
/// Pumping a fixed number of frames is enough to let routing resolve.
Future<void> pumpAt(WidgetTester tester, String location) async {
  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp.router(
        theme: buildAppTheme(),
        localizationsDelegates: const [
          AppL10n.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppL10n.supportedLocales,
        routerConfig: buildRouter(initialLocation: location),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

Future<void> settleRoute(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 350));
}

void main() {
  testWidgets('sign-in has no tab bar', (tester) async {
    await pumpAt(tester, '/signin');
    expect(find.byType(AppBottomNav), findsNothing);
  });

  testWidgets('punch has no tab bar', (tester) async {
    // Outside the shell by design, so there is nothing to hide.
    await pumpAt(tester, '/punch');
    expect(find.byType(AppBottomNav), findsNothing);
  });

  testWidgets('the menu groups the enabled modules and closes', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpAt(tester, '/home');

    final dock = find.byType(AppBottomNav);
    expect(dock, findsOneWidget);
    await tester.tap(find.descendant(of: dock, matching: find.text('Menu')));
    await settleRoute(tester);

    final menu = find.byType(WorkspaceMenu);
    expect(menu, findsOneWidget);
    expect(find.text('Time & requests'), findsOneWidget);
    expect(find.text('Workplace'), findsOneWidget);
    for (final branch in AppShell.branches) {
      expect(
        find.descendant(
          of: menu,
          matching: find.bySemanticsLabel(branch.label),
        ),
        branch.enabled ? findsOneWidget : findsNothing,
        reason: branch.label,
      );
    }

    await tester.tap(find.text('Close'));
    await settleRoute(tester);
    expect(menu, findsNothing);
    expect(dock, findsOneWidget);
    handle.dispose();
  });

  testWidgets('quick repeated close taps leave the original page in place', (
    tester,
  ) async {
    await pumpAt(tester, '/home');
    await tester.tap(find.text('Menu'));
    await settleRoute(tester);

    final center = tester.getCenter(find.text('Close'));
    await tester.tapAt(center);
    await tester.pump(const Duration(milliseconds: 45));
    await tester.tapAt(center);
    await settleRoute(tester);

    expect(find.byType(WorkspaceMenu), findsNothing);
    expect(find.byType(AppBottomNav), findsOneWidget);
    await tester.tap(find.text('Menu'));
    await settleRoute(tester);
    expect(find.byType(WorkspaceMenu), findsOneWidget);
  });

  testWidgets('choosing Requests from the menu switches branch', (
    tester,
  ) async {
    await pumpAt(tester, '/home');
    await tester.tap(find.text('Menu'));
    await settleRoute(tester);
    await tester.tap(find.text('Requests'));
    await settleRoute(tester);
    await settleRoute(tester);

    expect(find.byType(WorkspaceMenu), findsNothing);
    expect(find.byType(RequestsScreen), findsOneWidget);
  });

  testWidgets('deep-linking into a switched-off module explains itself', (
    tester,
  ) async {
    // A push notification from a server whose modules do not match the app is
    // exactly how someone lands here; it must not be a blank screen. Payroll
    // and requests both widened back on once their screens were built, so
    // helpdesk -- not built at all -- is what still has a stub for this.
    expect(Modules.helpdesk, isFalse, reason: 'guards the assertion below');
    await pumpAt(tester, '/requests/helpdesk');

    expect(find.text('NOT AVAILABLE YET'), findsOneWidget);
  });

  testWidgets('a detail screen inside a branch keeps its tab bar', (
    tester,
  ) async {
    // /time/leave is a child of the Records branch.
    await pumpAt(tester, '/time/leave');

    expect(find.byType(AppBottomNav), findsOneWidget);
    expect(find.text('Leave'), findsWidgets);
  });

  testWidgets('tapping a tab switches branch', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpAt(tester, '/home');

    await tester.tap(
      find.descendant(
        of: find.byType(AppBottomNav),
        matching: find.bySemanticsLabel('Records'),
      ),
    );
    await settleRoute(tester);

    expect(find.byType(AttendanceScreen), findsOneWidget);
    handle.dispose();
  });
}
