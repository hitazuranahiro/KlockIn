import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';
import 'glass_surface.dart';
import 'pressable.dart';

class AppBottomNav extends StatelessWidget {
  const AppBottomNav({
    super.key,
    required this.leading,
    required this.trailing,
    required this.onMenu,
  });

  final ({AppNavItem item, bool selected, VoidCallback onTap}) leading;
  final ({AppNavItem item, bool selected, VoidCallback onTap})? trailing;
  final VoidCallback onMenu;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(16, 4, 16, 10),
      child: Center(
        heightFactor: 1,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 500),
          child: GlassSurface(
            radius: 30,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            child: Row(
              children: [
                Expanded(
                  child: _DestinationButton(
                    item: leading.item,
                    selected: leading.selected,
                    onTap: leading.onTap,
                  ),
                ),
                AppMenuButton(onTap: onMenu),
                Expanded(
                  child: trailing == null
                      ? const SizedBox.shrink()
                      : _DestinationButton(
                          item: trailing!.item,
                          selected: trailing!.selected,
                          onTap: trailing!.onTap,
                        ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class AppNavItem {
  const AppNavItem({required this.label, required this.icon});

  final String label;
  final IconData icon;
}

/// The same center control opens the menu and dismisses it from the same area.
class AppMenuButton extends StatelessWidget {
  const AppMenuButton({super.key, required this.onTap, this.isOpen = false});

  final VoidCallback onTap;
  final bool isOpen;

  @override
  Widget build(BuildContext context) {
    final label = isOpen ? 'Close' : 'Menu';
    return Semantics(
      button: true,
      label: isOpen ? 'Close workspace menu' : 'Menu',
      onTap: onTap,
      excludeSemantics: true,
      child: Pressable(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minWidth: 74, minHeight: 67),
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 7),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.pill),
            border: Border.all(color: const Color(0xFF90B9FF)),
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF276AE8), Color(0xFF123CA0)],
            ),
            boxShadow: const [
              BoxShadow(
                color: Color(0x472154C6),
                blurRadius: 12,
                offset: Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                isOpen ? Icons.close_rounded : Icons.grid_view_rounded,
                size: 21,
                color: Colors.white,
              ),
              const SizedBox(height: 3),
              Text(
                label,
                style: AppText.tabLabel.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DestinationButton extends StatelessWidget {
  const _DestinationButton({
    required this.item,
    required this.selected,
    required this.onTap,
  });

  final AppNavItem item;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? AppColors.brandStrong : AppColors.ink3;
    return Semantics(
      button: true,
      selected: selected,
      label: item.label,
      onTap: onTap,
      excludeSemantics: true,
      child: Pressable(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 58),
          margin: const EdgeInsets.symmetric(horizontal: 5),
          padding: const EdgeInsets.all(5),
          decoration: BoxDecoration(
            color: selected ? AppColors.brandTint : Colors.transparent,
            borderRadius: BorderRadius.circular(AppRadii.card),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(item.icon, size: 21, color: foreground),
              const SizedBox(height: 4),
              Text(
                item.label,
                textAlign: TextAlign.center,
                style: AppText.tabLabel.copyWith(
                  color: foreground,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
