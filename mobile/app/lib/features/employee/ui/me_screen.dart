// Modified for KlockIN by Tomeku, 2026-11-25.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../../core/auth/biometric_lock.dart';
import '../../../core/auth/session.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_primitives.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../auth/ui/server_settings_screen.dart';
import '../data/profile_api.dart';

final _appVersionProvider = FutureProvider<String>((ref) async {
  final info = await PackageInfo.fromPlatform();
  return '${info.version} (${info.buildNumber})';
});

class MeScreen extends ConsumerWidget {
  const MeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final version = ref.watch(_appVersionProvider).value;
    final canEdit = ref.watch(canEditProfileProvider);
    final biometricAvailable =
        ref.watch(biometricAvailableProvider).value ?? false;
    final biometricEnabled = ref.watch(biometricEnabledProvider);
    final name = session?.user.fullName ?? 'Signed out';

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          const AppTopBar(title: 'Account'),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                AppSpace.screen,
                AppSpace.x12,
                AppSpace.screen,
                AppSpace.scrollBottom,
              ),
              children: [
                Container(
                  decoration: BoxDecoration(
                    color: AppColors.brandTint,
                    border: Border.all(color: AppColors.brandTintBorder),
                    borderRadius: BorderRadius.circular(AppRadii.card),
                  ),
                  padding: const EdgeInsets.all(AppSpace.x16),
                  child: Row(
                    children: [
                      AppAvatar.toned(name: name, size: 50),
                      const SizedBox(width: AppSpace.x14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(name, style: AppText.appBarTitle),
                            if (session != null) ...[
                              const SizedBox(height: AppSpace.x4),
                              Text(
                                _roleLabel(session.capabilities.role),
                                style: AppText.meta.copyWith(
                                  color: AppColors.brandTintInk,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                if (session?.isCleartext == true) ...[
                  const SizedBox(height: AppSpace.x12),
                  Container(
                    color: AppColors.warningBg,
                    padding: const EdgeInsets.all(AppSpace.x12),
                    child: const Text(
                      'This connection is not encrypted.',
                      style: TextStyle(color: AppColors.warningInk),
                    ),
                  ),
                ],
                const SizedBox(height: AppSpace.x28),
                const SectionHeader(title: 'Personal'),
                const SizedBox(height: AppSpace.x6),
                _AccountRow(
                  icon: Icons.badge_outlined,
                  label: 'Personal information',
                  detail: canEdit ? null : 'Managed by HR',
                  onTap: canEdit
                      ? () => context.push('/me/personal-information')
                      : null,
                ),
                _AccountRow(
                  icon: Icons.notifications_none_rounded,
                  label: 'Notifications',
                  onTap: () => context.go('/home/notifications'),
                ),
                const SizedBox(height: AppSpace.x20),
                const SectionHeader(title: 'Device and access'),
                const SizedBox(height: AppSpace.x6),
                if (session?.faceDetectionEnabled == true)
                  _AccountRow(
                    icon: Icons.face_retouching_natural_outlined,
                    label: 'Attendance face setup',
                    onTap: () => context.push('/me/face-enrolment'),
                  ),
                if (biometricAvailable)
                  _AccountRow(
                    icon: Icons.lock_outline_rounded,
                    label: 'Biometric unlock',
                    trailing: Switch(
                      value: biometricEnabled,
                      activeThumbColor: AppColors.surface,
                      activeTrackColor: AppColors.brandStrong,
                      onChanged: (value) => ref
                          .read(biometricEnabledProvider.notifier)
                          .set(value),
                    ),
                  ),
                _AccountRow(
                  icon: Icons.dns_outlined,
                  label: 'Server settings',
                  detail: _hostOnly(session?.host),
                  onTap: () => Navigator.of(context).push<void>(
                    MaterialPageRoute(
                      builder: (_) => ServerSettingsScreen(
                        initialAddress: session?.host ?? '',
                        allowUse: false,
                      ),
                    ),
                  ),
                ),
                const Divider(height: 1, color: AppColors.line),
                const SizedBox(height: AppSpace.x20),
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: TextButton.icon(
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.danger,
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpace.x10,
                      ),
                    ),
                    onPressed: () =>
                        ref.read(sessionProvider.notifier).signOut(),
                    icon: const Icon(Icons.logout_rounded, size: 19),
                    label: const Text('Sign out'),
                  ),
                ),
                const SizedBox(height: AppSpace.x14),
                Text(
                  ['KlockIN by Tomeku', ?version].join(' · '),
                  style: AppText.meta,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String? _hostOnly(String? host) =>
      host == null ? null : Uri.tryParse(host)?.host;

  static String _roleLabel(String role) => switch (role) {
    'hrexec' => 'HR executive',
    'manager' => 'Manager',
    _ => 'Employee',
  };
}

class _AccountRow extends StatelessWidget {
  const _AccountRow({
    required this.icon,
    required this.label,
    this.detail,
    this.onTap,
    this.trailing,
  });

  final IconData icon;
  final String label;
  final String? detail;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Divider(height: 1, color: AppColors.line),
        InkWell(
          onTap: onTap,
          child: Container(
            constraints: const BoxConstraints(minHeight: 56),
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpace.x4,
              vertical: AppSpace.x8,
            ),
            child: Row(
              children: [
                Icon(icon, size: 21, color: AppColors.ink3),
                const SizedBox(width: AppSpace.x12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(label, style: AppText.cardTitle),
                      if (detail != null) ...[
                        const SizedBox(height: AppSpace.x4),
                        Text(detail!, style: AppText.meta),
                      ],
                    ],
                  ),
                ),
                if (trailing != null)
                  Semantics(label: label, child: trailing!)
                else if (onTap != null)
                  const Icon(
                    Icons.chevron_right,
                    size: 19,
                    color: AppColors.ink3,
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
