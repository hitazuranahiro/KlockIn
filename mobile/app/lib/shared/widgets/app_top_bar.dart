import 'package:flutter/material.dart';

import '../../core/theme/platform_chrome.dart';
import '../../core/theme/tokens.dart';
import 'pressable.dart';

/// A shared title row for page and detail navigation.
class AppTopBar extends StatelessWidget {
  const AppTopBar({
    super.key,
    required this.title,
    this.onBack,
    this.trailing,
    this.subtitle,
    this.onDark = false,
  });

  final String title;

  /// Shows a back control when set.
  final VoidCallback? onBack;
  final Widget? trailing;

  /// Mono sub-line under the title, for context such as a reference number.
  final String? subtitle;

  /// For full-bleed ink screens (the punch confirmation).
  final bool onDark;

  @override
  Widget build(BuildContext context) {
    final titleColor = onDark ? AppColors.surface : AppColors.ink;

    return Padding(
      padding: PlatformChrome.appBarPaddingOf(context),
      child: Row(
        children: [
          if (onBack != null) ...[
            CircleBackButton(onTap: onBack!),
            const SizedBox(width: AppSpace.x10),
          ],
          Expanded(
            child: Semantics(
              header: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.appBarTitle.copyWith(color: titleColor),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppText.mono.copyWith(
                        fontSize: 11,
                        color: onDark ? AppColors.onDark2 : AppColors.ink3,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: AppSpace.x10),
            trailing!,
          ],
        ],
      ),
    );
  }
}

/// A compact back control with a full-size touch target.
class CircleBackButton extends StatelessWidget {
  const CircleBackButton({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Back',
      onTap: onTap,
      excludeSemantics: true,
      child: Pressable(
        onTap: onTap,
        child: SizedBox(
          width: kMinHitTarget,
          height: kMinHitTarget,
          child: Center(
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(AppRadii.field),
                border: Border.all(color: AppColors.line),
              ),
              child: const Icon(
                Icons.arrow_back_rounded,
                size: 19,
                color: AppColors.ink,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A brand-coloured text action for the app bar's trailing slot
/// ("Edit", "Mark read").
class TopBarAction extends StatelessWidget {
  const TopBarAction({super.key, required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: Pressable(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kMinHitTarget),
          child: Center(
            child: Text(
              label,
              style: AppText.cardTitle.copyWith(
                color: AppColors.brandStrong,
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
