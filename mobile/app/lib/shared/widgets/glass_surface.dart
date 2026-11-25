import 'dart:ui';

import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';

/// A frosted surface for a short list of high-priority UI layers.
class GlassSurface extends StatelessWidget {
  const GlassSurface({
    super.key,
    required this.child,
    this.padding = EdgeInsets.zero,
    this.radius = AppRadii.card,
    this.tint = AppColors.surface,
    this.blur = 18,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;
  final Color tint;
  final double blur;

  @override
  Widget build(BuildContext context) {
    final highContrast = MediaQuery.highContrastOf(context);
    final borderRadius = BorderRadius.circular(radius);
    final panel = DecoratedBox(
      decoration: BoxDecoration(
        color: highContrast
            ? AppColors.surface
            : tint.withValues(alpha: tint.a * 0.82),
        borderRadius: borderRadius,
        border: Border.all(
          color: highContrast ? AppColors.line3 : AppColors.surface,
        ),
      ),
      child: Padding(padding: padding, child: child),
    );

    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: borderRadius,
        boxShadow: highContrast ? null : AppShadows.floating,
      ),
      child: ClipRRect(
        borderRadius: borderRadius,
        child: highContrast || blur == 0
            ? panel
            : BackdropFilter(
                filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
                child: panel,
              ),
      ),
    );
  }
}
