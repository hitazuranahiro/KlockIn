// KlockIN by Tomeku.
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void mockScreenshotConnectivity() {
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const status = MethodChannel('dev.fluttercommunity.plus/connectivity_status');
  const connectivity = MethodChannel('dev.fluttercommunity.plus/connectivity');
  messenger.setMockMethodCallHandler(status, (_) async => null);
  messenger.setMockMethodCallHandler(connectivity, (_) async => ['wifi']);
  addTearDown(() {
    messenger.setMockMethodCallHandler(status, null);
    messenger.setMockMethodCallHandler(connectivity, null);
  });
}

Future<void> loadScreenshotFonts() async {
  Future<void> family(String name, List<String> files) async {
    final loader = FontLoader(name);
    for (final file in files) {
      loader.addFont(
        File(file).readAsBytes().then((bytes) => ByteData.view(bytes.buffer)),
      );
    }
    await loader.load();
  }

  const fonts = 'Assets/fonts';
  await family('Inter', [
    for (final weight in ['Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold'])
      '$fonts/inter/Inter-$weight.ttf',
  ]);
  await family('JetBrainsMono', [
    for (final weight in ['Regular', 'Medium', 'Bold'])
      '$fonts/JetBrainsMono-$weight.ttf',
  ]);
  final cache = File(Platform.resolvedExecutable).parent.parent.parent.parent;
  await family('MaterialIcons', [
    '${cache.path}/artifacts/material_fonts/MaterialIcons-Regular.otf',
  ]);
}
