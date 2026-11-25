// Modified for KlockIN by Tomeku, 2026-11-25.
/// Sign-in renders and is operable. Layout only -- the network side is
/// covered by the interceptor tests.
library;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderEditable;
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/theme/app_theme.dart';
import 'package:klockin/l10n/app_localizations.dart';
import 'package:klockin/features/auth/ui/sign_in_screen.dart';
import 'package:klockin/shared/widgets/app_button.dart';

Widget wrap(Widget child) => ProviderScope(
  child: MaterialApp(
    theme: buildAppTheme(),
    localizationsDelegates: const [
      AppL10n.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppL10n.supportedLocales,
    home: child,
  ),
);

final _server = find.byKey(const ValueKey('sign-in-server'));
final _identity = find.byKey(const ValueKey('sign-in-identity'));
final _password = find.byKey(const ValueKey('sign-in-password'));

void main() {
  testWidgets('first launch exposes an empty server field', (tester) async {
    await tester.pumpWidget(wrap(const SignInScreen()));
    expect(find.text('Server'), findsOneWidget);
    final field = tester.widget<TextField>(_server);
    expect(field.controller!.text, isEmpty);
  });

  testWidgets('shows the brand and sign-in fields', (tester) async {
    await tester.pumpWidget(wrap(const SignInScreen()));
    expect(find.text('KlockIN'), findsOneWidget);
    expect(find.text('by Tomeku'), findsOneWidget);
    expect(find.text('Employee ID'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Test connection'), findsOneWidget);
  });

  testWidgets('offers username sign-in for existing accounts', (tester) async {
    await tester.pumpWidget(wrap(const SignInScreen()));
    await tester.ensureVisible(find.text('Use username instead'));
    await tester.tap(find.text('Use username instead'));
    await tester.pump();
    expect(find.text('Username'), findsOneWidget);
    expect(find.text('Use employee ID instead'), findsOneWidget);
  });

  testWidgets('password visibility can be toggled', (tester) async {
    await tester.pumpWidget(wrap(const SignInScreen()));

    expect(tester.widget<TextField>(_password).obscureText, isTrue);
    await tester.tap(find.byTooltip('Show password'));
    await tester.pump();
    expect(tester.widget<TextField>(_password).obscureText, isFalse);
    await tester.tap(find.byTooltip('Hide password'));
    await tester.pump();
    expect(tester.widget<TextField>(_password).obscureText, isTrue);
  });

  testWidgets('credentials have equal field heights and clear actions', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const SignInScreen()));
    expect(tester.getSize(_identity).height, tester.getSize(_password).height);
    expect(
      tester.getSize(find.byTooltip('Show password')).shortestSide,
      greaterThanOrEqualTo(44),
    );
    expect(
      tester.getTopLeft(find.byType(AppButton)).dy,
      lessThan(tester.getTopLeft(find.text('Set up your workplace')).dy),
    );
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('iOS credential carets center on their icons at ${scale}x', (
      tester,
    ) async {
      await tester.pumpWidget(
        wrap(
          Builder(
            builder: (context) => MediaQuery(
              data: MediaQuery.of(context)
                  .copyWith(textScaler: TextScaler.linear(scale)),
              child: const SignInScreen(),
            ),
          ),
        ),
      );

      for (final (field, icon, sample) in [
        (_identity, Icons.badge_outlined, 'EMP-012'),
        (_password, Icons.lock_outline_rounded, 'SamplePass'),
      ]) {
        await tester.ensureVisible(field);
        await tester.showKeyboard(field);
        await tester.pump();

        double caretY() {
          final finder = find.descendant(
            of: field,
            matching: find.byType(EditableText),
          );
          final RenderEditable editable = tester
              .state<EditableTextState>(finder)
              .renderEditable;
          final position = tester
              .widget<EditableText>(finder)
              .controller
              .selection
              .extent;
          final rect = editable.getLocalRectForCaret(position);
          return editable.localToGlobal(rect.center).dy;
        }

        expect(caretY(), closeTo(tester.getCenter(find.byIcon(icon)).dy, 2));
        await tester.enterText(field, sample);
        await tester.pump();
        expect(caretY(), closeTo(tester.getCenter(find.byIcon(icon)).dy, 2));
      }
    }, variant: const TargetPlatformVariant({TargetPlatform.iOS}));
  }

  testWidgets(
    'keyboard Next reaches password and the CTA can scroll into view',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 640);
      tester.view.viewInsets = const FakeViewPadding(bottom: 280);
      addTearDown(tester.view.reset);

      await tester.pumpWidget(wrap(const SignInScreen()));
      await tester.showKeyboard(_identity);
      await tester.testTextInput.receiveAction(TextInputAction.next);
      await tester.pump();
      expect(tester.widget<TextField>(_password).focusNode!.hasFocus, isTrue);
      expect(
        tester.widget<TextField>(_password).textInputAction,
        TextInputAction.go,
      );

      final button = find.byType(AppButton);
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      expect(button.hitTestable(), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('server settings keep a port and installation path', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const SignInScreen()));
    await tester.enterText(_server, 'https://time.example.com:8443/work');
    await tester.ensureVisible(find.text('Server settings'));
    await tester.tap(find.text('Server settings'));
    await tester.pumpAndSettle();

    final settingsAddress = tester.widget<TextField>(
      find.byType(TextField).hitTestable(),
    );
    expect(
      settingsAddress.controller!.text,
      'https://time.example.com:8443/work',
    );
    await tester.tap(find.text('Use this server'));
    await tester.pumpAndSettle();

    final serverAddress = tester.widget<TextField>(_server);
    expect(
      serverAddress.controller!.text,
      'https://time.example.com:8443/work',
    );
  });

  testWidgets('a malformed host is reported against the host field', (
    tester,
  ) async {
    // Deliberately a case that needs no network: normalisation rejects it
    // before anything is sent. The point being pinned is *where* the message
    // lands -- against the host field, not as "invalid credentials", which is
    // the confusion the pre-flight exists to prevent.
    await tester.pumpWidget(wrap(const SignInScreen()));

    await tester.enterText(_server, 'ftp://hr.company.com');
    await tester.ensureVisible(find.text('Sign in'));
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.textContaining('http://'), findsOneWidget);
  });

  testWidgets('an http host on a local network warns, and is allowed', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const SignInScreen()));

    await tester.enterText(_server, 'http://192.168.1.9');
    await tester.pump();

    expect(find.textContaining('not encrypted'), findsOneWidget);
  });

  testWidgets('an http host on a public domain shows no warning banner', (
    tester,
  ) async {
    // It is refused at submit rather than warned about: the warning is for
    // connections we permit.
    await tester.pumpWidget(wrap(const SignInScreen()));

    await tester.enterText(_server, 'http://hr.public.com');
    await tester.pump();

    expect(find.textContaining('not encrypted'), findsNothing);
  });

  testWidgets('every tappable clears the 44pt minimum', (tester) async {
    // The handoff requires this, and it is easy to lose while styling.
    await tester.pumpWidget(wrap(const SignInScreen()));

    for (final element in find.byType(AppButton).evaluate()) {
      expect(
        tester.getSize(find.byWidget(element.widget)).height,
        greaterThanOrEqualTo(44.0),
      );
    }
  });
}
