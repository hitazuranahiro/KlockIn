// Modified for KlockIN by Tomeku, 2026-11-25.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

ThemeData buildAppTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: AppColors.brandStrong,
    primary: AppColors.brandStrong,
    surface: AppColors.surface,
    error: AppColors.danger,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: AppColors.bg,
    // The design has no ink-splash language; presses are expressed as border
    // and fill changes on the components themselves.
    splashFactory: NoSplash.splashFactory,
    highlightColor: Colors.transparent,
    dividerColor: AppColors.line,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bg,
      foregroundColor: AppColors.ink,
      surfaceTintColor: Colors.transparent,
    ),
    textSelectionTheme: const TextSelectionThemeData(
      cursorColor: AppColors.brandStrong,
      selectionHandleColor: AppColors.brandStrong,
    ),
  );
}
