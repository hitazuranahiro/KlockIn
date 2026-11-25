// Modified for KlockIN by Tomeku, 2026-11-25.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'features/punch/data/punch_background_sync.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  unawaited(initializePunchBackgroundSync());
  runApp(const ProviderScope(child: KlockInApp()));
}
