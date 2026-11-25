import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';
import 'package:klockin/features/punch/ui/attendance_sync_card.dart';

void main() {
  testWidgets('the latest synced punch shows its detected address on Home', (
    tester,
  ) async {
    const address = 'Makati, Metro Manila';
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          pendingPunchCountProvider.overrideWith((ref) async => 0),
          recentPunchesProvider.overrideWith(
            (ref) async => [
              QueuedPunch(
                uuid: 'receipt',
                isClockingIn: true,
                at: DateTime.utc(2026, 11, 25, 8),
                deviceId: 'device',
                latitude: 14.5,
                longitude: 121,
                selfie: null,
                state: PunchSyncState.synced,
                detectedAddress: address,
              ),
            ],
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: AttendanceSyncCard())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Latest punch synced'), findsOneWidget);
    expect(find.text('Detected address · $address'), findsOneWidget);
  });

  testWidgets('a recoverable refusal shows its next step and remains queued', (
    tester,
  ) async {
    const reason =
        'Ask HR to reset the linked device, then sign in here and sync again.';
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          pendingPunchCountProvider.overrideWith((ref) async => 1),
          recentPunchesProvider.overrideWith(
            (ref) async => [
              QueuedPunch(
                uuid: 'pending-punch',
                isClockingIn: true,
                at: DateTime.utc(2026, 11, 25, 8),
                deviceId: 'device',
                latitude: 0,
                longitude: 0,
                selfie: null,
                error: reason,
              ),
            ],
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: AttendanceSyncCard())),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('1 waiting to sync'), findsOneWidget);
    expect(find.text('Sync now'), findsOneWidget);
    expect(find.textContaining('Sync paused. $reason'), findsOneWidget);
    expect(find.text('Latest punch needs attention'), findsNothing);
  });
}
