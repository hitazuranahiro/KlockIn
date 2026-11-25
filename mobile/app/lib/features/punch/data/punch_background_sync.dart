import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:workmanager/workmanager.dart';

import '../../../core/auth/session.dart';
import 'punch_queue.dart';
import 'punch_sync.dart';

const _punchSyncTask = 'com.tomeku.klockin.attendance-sync';
Future<void>? _initialization;

Future<void> initializePunchBackgroundSync() {
  return _initialization ??= _initialize();
}

Future<void> _initialize() async {
  if (!supportsOfflinePunches) return;
  try {
    await Workmanager().initialize(punchSyncDispatcher);
    if (defaultTargetPlatform == TargetPlatform.android) {
      await Workmanager().registerPeriodicTask(
        _punchSyncTask,
        _punchSyncTask,
        frequency: const Duration(minutes: 15),
        constraints: Constraints(networkType: NetworkType.connected),
        existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
      );
    }
  } catch (exception) {
    debugPrint(
      'KlockIN background sync could not start: ${exception.runtimeType}',
    );
  }
}

Future<void> schedulePunchBackgroundSync() async {
  if (!supportsOfflinePunches) return;
  await initializePunchBackgroundSync();
  await _schedule();
}

Future<void> _schedule() async {
  final constraints = Constraints(networkType: NetworkType.connected);
  try {
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      await Workmanager().registerProcessingTask(
        _punchSyncTask,
        _punchSyncTask,
        constraints: constraints,
      );
    } else {
      await Workmanager().registerOneOffTask(
        '$_punchSyncTask-now',
        _punchSyncTask,
        constraints: constraints,
        initialDelay: const Duration(seconds: 10),
        existingWorkPolicy: ExistingWorkPolicy.keep,
      );
    }
  } catch (exception) {
    debugPrint(
      'KlockIN background sync scheduling failed: ${exception.runtimeType}',
    );
  }
}

@pragma('vm:entry-point')
void punchSyncDispatcher() {
  Workmanager().executeTask((task, _) async {
    DartPluginRegistrant.ensureInitialized();
    final container = ProviderContainer();
    try {
      await container
          .read(sessionProvider.notifier)
          .restore(attendanceOnly: true);
      final session = container.read(sessionProvider);
      if (session == null || session.user.id <= 0) return true;
      final queue = container.read(punchQueueProvider);
      final account = punchQueueAccount(session);

      await container.read(punchSyncProvider).flush(background: true);
      final drained = await queue.pendingCount(account) == 0;
      if (!drained && defaultTargetPlatform == TargetPlatform.iOS)
        await _schedule();
      return drained;
    } catch (_) {
      return false;
    } finally {
      container.dispose();
    }
  });
}
