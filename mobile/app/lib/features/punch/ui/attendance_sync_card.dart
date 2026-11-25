import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/tokens.dart';
import '../data/punch_queue.dart';
import '../data/punch_sync.dart';

class AttendanceSyncCard extends ConsumerWidget {
  const AttendanceSyncCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!supportsOfflinePunches) return const SizedBox.shrink();

    final recent =
        ref.watch(recentPunchesProvider).value ?? const <QueuedPunch>[];
    final pending = ref.watch(pendingPunchCountProvider).value ?? 0;
    final lastSync = ref.watch(lastSuccessfulPunchSyncProvider).value;
    final latest = recent.firstOrNull;
    final address = latest?.detectedAddress;
    if (pending == 0 && latest == null && lastSync == null) {
      return const SizedBox.shrink();
    }

    final deferred = recent.where(
      (punch) => punch.state == PunchSyncState.pending && punch.error != null,
    );
    final rejected = recent.where(
      (punch) => punch.state == PunchSyncState.rejected,
    );
    final (icon, label, color) = switch (latest?.state) {
      PunchSyncState.pending => (
        Icons.cloud_upload_outlined,
        '$pending waiting to sync',
        AppColors.warningInk,
      ),
      PunchSyncState.synced => (
        Icons.cloud_done_outlined,
        'Latest punch synced',
        AppColors.success,
      ),
      PunchSyncState.review => (
        Icons.schedule_outlined,
        'Server received the punch · attendance pending',
        AppColors.warningInk,
      ),
      PunchSyncState.rejected => (
        Icons.error_outline,
        'Latest punch needs attention',
        AppColors.danger,
      ),
      null => (Icons.cloud_done_outlined, 'Up to date', AppColors.success),
    };

    return Padding(
      padding: const EdgeInsets.only(top: AppSpace.x16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Divider(height: 1, color: AppColors.line),
          const SizedBox(height: AppSpace.x12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                pending > 0 ? Icons.cloud_upload_outlined : icon,
                size: 19,
                color: pending > 0 ? AppColors.warningInk : color,
              ),
              const SizedBox(width: AppSpace.x8),
              Expanded(
                child: Text(
                  pending > 0 ? '$pending waiting to sync' : label,
                  style: AppText.body.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          if (pending > 0)
            TextButton(
              onPressed: () => ref.read(punchSyncProvider).flush(),
              child: const Text('Sync now'),
            ),
          if (lastSync != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Last successful sync · ${DateFormat.yMMMd().add_Hm().format(lastSync.toLocal())}',
                style: AppText.meta,
              ),
            ),
          if (address != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('Detected address · $address', style: AppText.meta),
            ),
          for (final punch in deferred.take(3))
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                '${DateFormat.Md().add_Hm().format(punch.displayedAt.toLocal())} · '
                '${punch.isClockingIn ? 'Clock in' : 'Clock out'} · '
                'Sync paused. ${punch.error}',
                style: AppText.meta.copyWith(color: AppColors.warningInk),
              ),
            ),
          for (final punch in rejected.take(3))
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                '${DateFormat.Md().add_Hm().format(punch.displayedAt.toLocal())} · '
                '${punch.isClockingIn ? 'Clock in' : 'Clock out'} · '
                '${punch.error ?? 'Server declined'}',
                style: AppText.meta.copyWith(color: AppColors.danger),
              ),
            ),
        ],
      ),
    );
  }
}
