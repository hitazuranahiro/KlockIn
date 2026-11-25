import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/features/shell/ui/workspace_backdrop.dart';

Widget _backdrop({bool reduceMotion = false, bool visible = true}) {
  return Directionality(
    textDirection: TextDirection.ltr,
    child: MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: TickerMode(
        enabled: visible,
        child: const SizedBox.expand(child: WorkspaceBackdrop()),
      ),
    ),
  );
}

Future<int> _colorAtTop(WidgetTester tester) async {
  final paint = find.descendant(
    of: find.byType(WorkspaceBackdrop),
    matching: find.byType(CustomPaint),
  );
  final painter = tester.widget<CustomPaint>(paint).painter!;
  return (await tester.runAsync(() async {
    final recorder = ui.PictureRecorder();
    painter.paint(Canvas(recorder), const Size(64, 96));
    final picture = recorder.endRecording();
    final image = await picture.toImage(64, 96);
    final pixels = await image.toByteData();
    final color = pixels!.getUint32((12 * 64 + 51) * 4);
    image.dispose();
    picture.dispose();
    return color;
  }))!;
}

void main() {
  testWidgets('the visible gradient drifts and pauses when hidden', (
    tester,
  ) async {
    await tester.pumpWidget(_backdrop());
    await tester.pump();
    final start = await _colorAtTop(tester);
    await tester.pump(const Duration(seconds: 4));
    final moving = await _colorAtTop(tester);
    expect(moving, isNot(start));

    await tester.pumpWidget(_backdrop(visible: false));
    final paused = await _colorAtTop(tester);
    await tester.pump(const Duration(seconds: 4));
    expect(await _colorAtTop(tester), paused);
  });

  testWidgets('Reduce Motion keeps a static gradient', (tester) async {
    await tester.pumpWidget(_backdrop(reduceMotion: true));
    final start = await _colorAtTop(tester);
    await tester.pump(const Duration(seconds: 4));
    expect(await _colorAtTop(tester), start);
  });
}
