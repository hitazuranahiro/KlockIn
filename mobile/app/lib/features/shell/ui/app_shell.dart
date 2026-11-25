import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/scope.dart';
import '../../../shared/widgets/app_bottom_nav.dart';
import 'workspace_menu.dart';

/// The dock and menu share the same branch indices and their saved stacks.
class AppShell extends StatefulWidget {
  const AppShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  /// Router branch order stays stable when a module is disabled.
  static const branches = [
    (label: 'Today', icon: Icons.today_outlined, enabled: true),
    (
      label: 'Records',
      icon: Icons.receipt_long_outlined,
      enabled: Modules.attendance,
    ),
    (
      label: 'Requests',
      icon: Icons.assignment_outlined,
      enabled: Modules.requests,
    ),
    (label: 'People', icon: Icons.groups_outlined, enabled: Modules.employee),
    (label: 'Account', icon: Icons.manage_accounts_outlined, enabled: true),
  ];

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  bool _menuOpen = false;

  void _selectBranch(int index) {
    final shell = widget.navigationShell;
    shell.goBranch(index, initialLocation: index == shell.currentIndex);
  }

  ({AppNavItem item, bool selected, VoidCallback onTap}) _destination(
    int index,
  ) {
    final branch = AppShell.branches[index];
    return (
      item: AppNavItem(label: branch.label, icon: branch.icon),
      selected: index == widget.navigationShell.currentIndex,
      onTap: () => _selectBranch(index),
    );
  }

  WorkspaceShortcut? _shortcut(int index) {
    if (!AppShell.branches[index].enabled) return null;
    final destination = _destination(index);
    return WorkspaceShortcut(
      item: destination.item,
      selected: destination.selected,
      onTap: destination.onTap,
    );
  }

  Future<void> _openMenu() async {
    if (_menuOpen) return;
    _menuOpen = true;
    final router = GoRouter.of(context);
    final today = _shortcut(0);
    final records = _shortcut(1);
    final requests = _shortcut(2);
    final people = _shortcut(3);
    final account = _shortcut(4);
    try {
      final choose = await showWorkspaceMenu(context, [
        (
          title: 'Time & requests',
          shortcuts: [
            ?today,
            ?records,
            if (Modules.leave)
              WorkspaceShortcut(
                item: const AppNavItem(
                  label: 'Leave',
                  icon: Icons.event_available_outlined,
                ),
                onTap: () => router.go('/time/leave'),
              ),
            ?requests,
            if (Modules.payroll)
              WorkspaceShortcut(
                item: const AppNavItem(
                  label: 'Payslips',
                  icon: Icons.account_balance_wallet_outlined,
                ),
                onTap: () => router.go('/requests/payslips'),
              ),
          ],
        ),
        (
          title: 'Workplace',
          shortcuts: [
            ?people,
            ?account,
            WorkspaceShortcut(
              item: const AppNavItem(
                label: 'Notifications',
                icon: Icons.notifications_none_rounded,
              ),
              onTap: () => router.go('/home/notifications'),
            ),
          ],
        ),
      ]);
      if (mounted) choose?.call();
    } finally {
      _menuOpen = false;
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: widget.navigationShell,
    bottomNavigationBar: AppBottomNav(
      leading: _destination(0),
      trailing: AppShell.branches[1].enabled ? _destination(1) : null,
      onMenu: _openMenu,
    ),
  );
}
