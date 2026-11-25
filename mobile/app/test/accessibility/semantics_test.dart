// Modified for KlockIN by Tomeku, 2026-11-25.
/// What a screen reader hears, and what a finger can hit.
///
/// Icon-only controls are the risk: they read as nothing at all to anyone not
/// looking at the screen, and this app has several (back chevrons, the
/// notification bell, the punch shortcut, tab items).
library;

import 'dart:ui' show Tristate;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/theme/app_theme.dart';
import 'package:klockin/core/theme/tokens.dart';
import 'package:klockin/l10n/app_localizations.dart';
import 'package:klockin/shared/widgets/app_bottom_nav.dart';
import 'package:klockin/shared/widgets/app_button.dart';

Future<void> pump(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(402 * 3, 874 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp(
        theme: buildAppTheme(),
        localizationsDelegates: const [
          AppL10n.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppL10n.supportedLocales,
        home: Scaffold(body: child),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  AppBottomNav navigation({required bool recordsSelected}) {
    return AppBottomNav(
      leading: (
        item: const AppNavItem(label: 'Today', icon: Icons.today_outlined),
        selected: !recordsSelected,
        onTap: () {},
      ),
      trailing: (
        item: const AppNavItem(
          label: 'Records',
          icon: Icons.receipt_long_outlined,
        ),
        selected: recordsSelected,
        onTap: () {},
      ),
      onMenu: () {},
    );
  }

  testWidgets('the dock announces both shortcuts and the menu', (tester) async {
    await pump(tester, navigation(recordsSelected: true));
    final handle = tester.ensureSemantics();

    for (final label in ['Today', 'Records', 'Menu']) {
      expect(find.text(label), findsOneWidget);
      expect(find.bySemanticsLabel(label), findsOneWidget);
    }
    final selected = tester.getSemantics(find.bySemanticsLabel('Records'));
    expect(selected.flagsCollection.isSelected, Tristate.isTrue);
    handle.dispose();
  });

  testWidgets('every dock control clears the 44pt minimum', (tester) async {
    await pump(tester, navigation(recordsSelected: false));
    final handle = tester.ensureSemantics();

    for (final label in ['Today', 'Records', 'Menu']) {
      final rect = tester.getRect(find.bySemanticsLabel(label));
      expect(rect.height, greaterThanOrEqualTo(kMinHitTarget), reason: label);
      expect(rect.width, greaterThanOrEqualTo(kMinHitTarget), reason: label);
    }
    handle.dispose();
  });

  testWidgets('a button announces its label and its disabled state', (
    tester,
  ) async {
    await pump(
      tester,
      const Column(
        children: [
          AppButton(label: 'Check out', onPressed: null),
          AppButton(label: 'Apply for leave'),
        ],
      ),
    );

    final handle = tester.ensureSemantics();

    final disabled = tester.getSemantics(find.bySemanticsLabel('Check out'));
    // Note: isButton is a plain bool while isSelected/isEnabled are Tristate.
    expect(disabled.flagsCollection.isButton, isTrue);
    expect(
      disabled.flagsCollection.isEnabled,
      isNot(Tristate.isTrue),
      reason: 'a greyed-out button must read as disabled, not just look it',
    );

    handle.dispose();
  });

  testWidgets('buttons clear the 44pt minimum even with short labels', (
    tester,
  ) async {
    await pump(tester, const AppButton(label: 'OK'));

    expect(
      tester.getSize(find.byType(AppButton)).height,
      greaterThanOrEqualTo(kMinHitTarget),
    );
  });
}
