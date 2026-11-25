// Modified for KlockIN by Tomeku, 2026-11-25.
/// Shared KlockIN color, spacing and type scales.
library;

import 'package:flutter/widgets.dart';

/// Clear blue, cool ink, and layered light surfaces.
abstract final class AppColors {
  static const brand = Color(0xFF104FCE);
  static const brandStrong = Color(0xFF104FCE);
  static const brandLight = Color(0xFF2162DC);
  static const brandPressed = Color(0xFF0C3DA6);
  static const brandTint = Color(0xFFE8F0FF);
  static const brandTintBorder = Color(0xFFC8DAFF);
  static const brandTintInk = Color(0xFF19478C);

  static const ink = Color(0xFF142B50); // primary text; dark hero surfaces
  static const ink2 = Color(0xFF314765); // secondary body
  static const ink3 = Color(0xFF506482); // labels, meta
  static const ink4 = Color(0xFF60718E); // muted meta, mono captions
  static const onDark2 = Color(0xFFC9D7F2); // secondary text on ink surfaces

  static const surface = Color(0xFFFFFFFF); // cards, app bars, tab bar
  static const bg = Color(0xFFEFF4FF); // screen background
  static const bg2 = Color(0xFFE5EDF9); // inset fields, quiet blocks

  static const line = Color(0xFFD8E4F6); // card borders
  static const line2 = Color(0xFFE6EEF9); // row dividers inside cards
  static const line3 = Color(0xFFB9CAE5); // dashed / attachment borders

  static const success = Color(0xFF1E7A54);
  static const successDot = Color(0xFF4CAF7D);
  static const warning = Color(0xFF9A6B12);
  static const warningBg = Color(0xFFFAF0DC);
  static const warningBorder = Color(0xFFEFDCB4);
  static const warningInk = Color(0xFF7A5410);
  static const danger = Color(0xFF8E2E22);
  static const dangerPressed = Color(0xFF73241B);
  static const dangerBg = Color(0xFFF7E4E0);
  static const dangerBorder = Color(0xFFE8BDB4);
  static const info = Color(0xFF2A5E8C);
  static const infoBg = Color(0xFFE6EEF5);
  static const infoBorder = Color(0xFFC9DBEA);
  static const infoInk = Color(0xFF1F4C74);

  /// Read status dot on the notifications screen.
  static const readDot = Color(0xFFD3E1F6);

  // Supporting surfaces and feedback.

  /// Divider for grouped content.
  static const cardBorder = Color(0xFFDAE5F6);

  /// Approved / resolved status chip fill.
  static const successBg = Color(0xFFE4F2EA);

  /// The toast's Undo action -- a light brand tone readable on ink.
  static const toastAction = Color(0xFFAFCEFF);

  /// Inset tiles and dividers on ink surfaces.
  static const onDarkTile = Color(0x12FFFFFF); // rgba(255,255,255,0.07)
  static const onDarkLine = Color(0x24FFFFFF); // rgba(255,255,255,0.14)
}

/// Spacing for the mobile screens.
abstract final class AppSpace {
  static const x4 = 4.0;
  static const x6 = 6.0;
  static const x8 = 8.0;
  static const x10 = 10.0;
  static const x12 = 12.0;
  static const x14 = 14.0;
  static const x16 = 16.0;
  static const x18 = 18.0;
  static const x20 = 20.0;
  static const x28 = 28.0;

  /// Horizontal screen padding.
  static const screen = x16;

  /// Scroll bodies end with this much breathing room.
  static const scrollBottom = x28;
}

/// Corner radii for controls and grouped content.
abstract final class AppRadii {
  static const chip = 20.0;
  static const pill = 9999.0;
  static const button = 18.0;
  static const field = 16.0;
  static const card = 24.0;
  static const hero = 28.0;
  static const tile = 12.0; // inset tiles inside a card
  static const iconTile = 12.0; // the 62pt quick-action tiles
  static const avatar = 12.0;
}

/// Type styles.
///
/// The platform UI font and `JetBrainsMono` for anything numeric, timestamped,
/// referenced or set in all-caps. Both are bundled -- see pubspec.
///
/// 10px is the floor in this product and is used only for mono eyebrow labels
/// and status chips.
abstract final class AppText {
  static const _mono = 'JetBrainsMono';

  /// 44/700 mono, tight. The punch clock, and nothing else.
  static const punchClock = TextStyle(
    fontFamily: _mono,
    fontSize: 44,
    fontWeight: FontWeight.w700,
    letterSpacing: -2,
    height: 1,
  );

  /// Screen hero number, e.g. net pay.
  static const heroNumber = TextStyle(
    fontFamily: _mono,
    fontSize: 33,
    fontWeight: FontWeight.w800,
    letterSpacing: -1.2,
  );

  static const statValue = TextStyle(
    fontFamily: _mono,
    fontSize: 24,
    fontWeight: FontWeight.w800,
    letterSpacing: -0.8,
  );

  /// Page and detail titles.
  static const appBarTitle = TextStyle(
    fontSize: 25,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.5,
    height: 1.2,
    color: AppColors.ink,
  );

  static const cardTitle = TextStyle(
    fontSize: 14.5,
    fontWeight: FontWeight.w700,
    height: 1.35,
  );

  static const body = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.5,
  );

  static const meta = TextStyle(
    fontSize: 11.5,
    fontWeight: FontWeight.w400,
    color: AppColors.ink3,
  );

  /// Uppercase mono section label.
  static const eyebrow = TextStyle(
    fontFamily: _mono,
    fontSize: 10,
    fontWeight: FontWeight.w700,
    letterSpacing: 1.1,
    color: AppColors.ink4,
  );

  static const statusChip = TextStyle(
    fontFamily: _mono,
    fontSize: 10,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.6,
  );

  static const tabLabel = TextStyle(fontSize: 11, fontWeight: FontWeight.w600);

  /// General-purpose mono, for timestamps and references inline.
  static const mono = TextStyle(
    fontFamily: _mono,
    fontSize: 12,
    fontWeight: FontWeight.w400,
  );
}

/// v2 shadows. v1 was flat; v2 lifts cards with a soft two-layer shadow and
/// gives the primary button and floating chrome their own.
///
/// Values are the handoff's CSS box-shadows. Negative spread is what keeps
/// the large blurs from reading as a grey halo.
abstract final class AppShadows {
  /// `0 1px 2px rgba(28,28,28,.04), 0 8px 24px -12px rgba(28,28,28,.10)`
  static const card = [
    BoxShadow(color: Color(0x0A1C1C1C), offset: Offset(0, 1), blurRadius: 2),
    BoxShadow(
      color: Color(0x1A1C1C1C),
      offset: Offset(0, 8),
      blurRadius: 24,
      spreadRadius: -12,
    ),
  ];

  /// Toast pill.
  static const toast = [
    BoxShadow(
      color: Color(0x991C1C1C),
      offset: Offset(0, 16),
      blurRadius: 36,
      spreadRadius: -14,
    ),
  ];

  /// Small floating controls: the back button, the logo tile.
  static const floating = [
    BoxShadow(color: Color(0x0F203F73), offset: Offset(0, 1), blurRadius: 2),
    BoxShadow(
      color: Color(0x26204078),
      offset: Offset(0, 6),
      blurRadius: 16,
      spreadRadius: -8,
    ),
  ];
}

/// Press feedback for interactive controls.
const double kPressScale = 0.97;
const Duration kPressDuration = Duration(milliseconds: 150);

/// Minimum touch target in logical pixels.
const double kMinHitTarget = 44;
