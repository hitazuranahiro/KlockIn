import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_bottom_nav.dart';
import '../../../shared/widgets/glass_surface.dart';
import '../../../shared/widgets/klockin_mark.dart';
import 'workspace_backdrop.dart';

class WorkspaceShortcut {
  const WorkspaceShortcut({
    required this.item,
    required this.onTap,
    this.selected = false,
  });

  final AppNavItem item;
  final VoidCallback onTap;
  final bool selected;
}

Future<VoidCallback?> showWorkspaceMenu(
  BuildContext context,
  List<({String title, List<WorkspaceShortcut> shortcuts})> groups,
) async {
  final reduceMotion = MediaQuery.disableAnimationsOf(context);
  final route = RawDialogRoute<VoidCallback>(
    barrierLabel: 'Close workspace menu',
    barrierColor: const Color(0x2225487C),
    barrierDismissible: false,
    transitionDuration: reduceMotion
        ? Duration.zero
        : const Duration(milliseconds: 320),
    pageBuilder: (_, animation, _) =>
        WorkspaceMenu(groups: groups, entrance: animation),
    transitionBuilder: (_, _, _, child) => child,
  );
  final shortcut = await Navigator.of(context, rootNavigator: true).push(route);
  await route.completed;
  return shortcut;
}

class WorkspaceMenu extends StatelessWidget {
  const WorkspaceMenu({
    super.key,
    required this.groups,
    this.entrance = const AlwaysStoppedAnimation(1),
  });

  final List<({String title, List<WorkspaceShortcut> shortcuts})> groups;
  final Animation<double> entrance;

  @override
  Widget build(BuildContext context) {
    void dismiss([VoidCallback? action]) {
      if (ModalRoute.isCurrentOf(context) ?? true) {
        Navigator.of(context).pop(action);
      }
    }

    final progress = MediaQuery.disableAnimationsOf(context)
        ? const AlwaysStoppedAnimation<double>(1)
        : entrance;
    return Semantics(
      scopesRoute: true,
      namesRoute: true,
      label: 'Workspace menu',
      explicitChildNodes: true,
      child: Material(
        type: MaterialType.transparency,
        child: Stack(
          fit: StackFit.expand,
          children: [
            FadeTransition(
              opacity: progress.drive(CurveTween(curve: Curves.easeOutCubic)),
              child: const WorkspaceBackdrop(),
            ),
            SafeArea(
              minimum: const EdgeInsets.fromLTRB(18, 12, 18, 15),
              child: Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 600),
                  child: Column(
                    children: [
                      _MenuReveal(
                        animation: progress,
                        interval: const Interval(
                          0.03,
                          0.72,
                          curve: Curves.easeOutCubic,
                        ),
                        offset: const Offset(0, 0.16),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(2, 0, 0, 16),
                          child: Row(
                            children: [
                              const Expanded(child: KlockInLockup()),
                              IconButton.filledTonal(
                                tooltip: 'Dismiss menu',
                                onPressed: dismiss,
                                icon: const Icon(Icons.close_rounded),
                              ),
                            ],
                          ),
                        ),
                      ),
                      Expanded(
                        child: _MenuReveal(
                          animation: progress,
                          interval: const Interval(
                            0.10,
                            0.93,
                            curve: Curves.easeOutCubic,
                          ),
                          offset: const Offset(0, 0.045),
                          child: ListView(
                            padding: const EdgeInsets.only(bottom: 20),
                            children: [
                              Semantics(
                                header: true,
                                child: Text(
                                  'Workspace',
                                  style: AppText.appBarTitle.copyWith(
                                    fontSize: 32,
                                    letterSpacing: -1,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 15),
                              for (final group in groups) ...[
                                GlassSurface(
                                  blur: 0,
                                  padding: const EdgeInsets.all(14),
                                  child: _ShortcutGroup(
                                    title: group.title,
                                    shortcuts: group.shortcuts,
                                    choose: (shortcut) =>
                                        dismiss(shortcut.onTap),
                                  ),
                                ),
                                const SizedBox(height: 13),
                              ],
                            ],
                          ),
                        ),
                      ),
                      _MenuReveal(
                        animation: progress,
                        interval: const Interval(
                          0,
                          0.65,
                          curve: Curves.easeOutCubic,
                        ),
                        offset: const Offset(0, 0.10),
                        child: AppMenuButton(isOpen: true, onTap: dismiss),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MenuReveal extends StatelessWidget {
  const _MenuReveal({
    required this.animation,
    required this.interval,
    required this.offset,
    required this.child,
  });

  final Animation<double> animation;
  final Interval interval;
  final Offset offset;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final progress = animation.drive(CurveTween(curve: interval));
    return FadeTransition(
      opacity: progress,
      child: SlideTransition(
        position: Tween(begin: offset, end: Offset.zero).animate(progress),
        child: child,
      ),
    );
  }
}

class _ShortcutGroup extends StatelessWidget {
  const _ShortcutGroup({
    required this.title,
    required this.shortcuts,
    required this.choose,
  });

  final String title;
  final List<WorkspaceShortcut> shortcuts;
  final ValueChanged<WorkspaceShortcut> choose;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 0, 4, 10),
          child: Semantics(
            header: true,
            child: Text(
              title,
              style: AppText.body.copyWith(
                color: AppColors.ink,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ),
        LayoutBuilder(
          builder: (context, constraints) {
            const gap = 6.0;
            final scale = MediaQuery.textScalerOf(context).scale(13) / 13;
            final columns = (constraints.maxWidth / (94 * scale)).floor().clamp(
              1,
              3,
            );
            final width =
                (constraints.maxWidth - gap * (columns - 1)) / columns;
            return Wrap(
              spacing: gap,
              runSpacing: gap,
              children: [
                for (final shortcut in shortcuts)
                  SizedBox(
                    width: width,
                    child: _ShortcutTile(
                      shortcut: shortcut,
                      onTap: () => choose(shortcut),
                    ),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _ShortcutTile extends StatelessWidget {
  const _ShortcutTile({required this.shortcut, required this.onTap});

  final WorkspaceShortcut shortcut;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = shortcut.selected
        ? AppColors.brandStrong
        : AppColors.ink2;
    return Semantics(
      label: shortcut.item.label,
      selected: shortcut.selected,
      button: true,
      onTap: onTap,
      excludeSemantics: true,
      child: Material(
        color: shortcut.selected
            ? const Color(0xFFDCE9FF)
            : const Color(0x80EAF1FE),
        borderRadius: BorderRadius.circular(17),
        child: InkWell(
          borderRadius: BorderRadius.circular(17),
          onTap: onTap,
          child: Container(
            constraints: const BoxConstraints(minHeight: 83),
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 10),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(shortcut.item.icon, size: 23, color: foreground),
                const SizedBox(height: 6),
                Text(
                  shortcut.item.label,
                  textAlign: TextAlign.center,
                  style: AppText.body.copyWith(
                    color: foreground,
                    fontSize: 13,
                    fontWeight: shortcut.selected
                        ? FontWeight.w800
                        : FontWeight.w600,
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
