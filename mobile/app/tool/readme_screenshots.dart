// Modified for KlockIN by Tomeku, 2026-11-25.
/// Captures KlockIN screens with the preview's sample data.
///
///     flutter test tool/readme_screenshots.dart
///
/// Writes PNGs to ../docs/screenshots/preview/ unless KLOCKIN_SCREENSHOT_DIR
/// overrides it. A widget test rather than a simulator
/// run so it needs no device, no server and no sign-in, and produces the same
/// pictures every time. Lives outside test/ so `flutter test` never runs it.
library;

import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:klockin/app.dart';
import 'package:klockin/features/punch/data/punch_sync.dart';
import 'package:klockin/main_preview.dart';

import 'screenshot_support.dart';

const _shots = {
  'home': '/home',
  'attendance': '/time',
  'leave': '/time/leave',
  'leave-apply': '/time/leave/apply',
  'approvals': '/team/approvals',
  'team': '/team',
  'announcements': '/home/announcements',
  'announcement': '/home/announcements/1',
  'notifications': '/home/notifications',
  'me': '/me',
};

void main() {
  testWidgets('README screenshots', (tester) async {
    mockScreenshotConnectivity();
    await tester.runAsync(loadScreenshotFonts);
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    // Phone viewport rendered at 3x.
    tester.view
      ..physicalSize = const Size(1179, 2556)
      ..devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    final boundary = GlobalKey();
    await tester.pumpWidget(
      RepaintBoundary(
        key: boundary,
        child: ProviderScope(
          overrides: [
            ...previewOverrides,
            punchConnectionProvider.overrideWithValue(() async => false),
          ],
          child: const KlockInApp(),
        ),
      ),
    );
    await tester.pump(const Duration(seconds: 1));

    final outputDirectory =
        Platform.environment['KLOCKIN_SCREENSHOT_DIR'] ??
        '../docs/screenshots/preview';
    final out = Directory(outputDirectory)..createSync(recursive: true);
    for (final MapEntry(key: name, value: path) in _shots.entries) {
      GoRouter.of(tester.element(find.byType(Scaffold).first)).go(path);
      // The punch clock ticks forever, so settle by time, not pumpAndSettle.
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      // Asset images decode asynchronously; a test frame won't wait for them.
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
    debugDefaultTargetPlatformOverride = null;
  });
}
