// Modified for KlockIN by Tomeku, 2026-11-25.
/// Preparing and submitting a punch.
///
/// The whole flow lives here rather than in the widget so it can be tested
/// without hardware: read a position, work out where that is relative to the
/// fence, then submit. Only [LocationService] touches the device, and it is
/// injected.
library;

import 'package:uuid/uuid.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/auth/session.dart';
import '../../home/data/home_models.dart';
import 'geofence.dart';
import 'location_service.dart';
import 'punch_device.dart';
import 'punch_queue.dart';
import 'punch_sync.dart';

/// What the confirm screen knows before anyone taps.
@immutable
class PunchPreparation {
  const PunchPreparation({
    required this.isClockingIn,
    this.coordinates,
    this.fence,
    this.locationFailure,
    this.locationCheckPending = false,
  });

  final bool isClockingIn;
  final Coordinates? coordinates;
  final FencePosition? fence;
  final LocationFailure? locationFailure;
  final bool locationCheckPending;

  /// Whether the punch button should be live.
  ///
  /// The handoff requires the fence state to be resolved before the button
  /// enables. Where a fence is enforced and the person is outside it, the app
  /// does not offer a button that the server will refuse -- being told "no"
  /// before tapping is better than after.
  bool get canSubmit {
    if (locationFailure != null || coordinates == null) return false;
    if (fence == null) return true; // no fence configured, or not required
    return fence!.isInside;
  }

  String? get blockedReason {
    if (locationFailure != null) return locationFailure!.message;
    if (fence != null && !fence!.isInside) {
      return 'You are ${formatDistance(fence!.metresOutside)} outside the nearest '
          'allowed work location. Move closer to clock '
          '${isClockingIn ? 'in' : 'out'}.';
    }
    return null;
  }
}

class PunchController {
  PunchController(this._ref);

  final Ref _ref;

  /// Reads a position and evaluates it against the fence.
  ///
  /// A location failure is returned rather than thrown: the screen still has
  /// something to render, and the person still needs to be told which of the
  /// several location problems they have.
  Future<PunchPreparation> prepare({
    required bool isClockingIn,
    required GeofenceState geofence,
  }) async {
    try {
      final coordinates = await _ref.read(locationServiceProvider).current();
      return PunchPreparation(
        isClockingIn: isClockingIn,
        coordinates: coordinates,
        fence: geofence.enabled
            ? _nearestAllowedFence(geofence, coordinates)
            : null,
        locationCheckPending:
            !geofence.known ||
            (geofence.enabled && geofence.allowedLocations.isEmpty),
      );
    } on LocationFailure catch (failure) {
      return PunchPreparation(
        isClockingIn: isClockingIn,
        locationFailure: failure,
      );
    }
  }

  FencePosition? _nearestAllowedFence(
    GeofenceState policy,
    Coordinates coordinates,
  ) {
    FencePosition? nearest;
    for (final site in policy.allowedLocations) {
      final position = evaluateFence(
        fenceLatitude: site.latitude,
        fenceLongitude: site.longitude,
        radiusInMetres: site.radiusInMeters,
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
        siteName: site.name,
      );
      if (position == null) continue;
      if (position.isInside) return position;
      if (nearest == null || position.metresOutside < nearest.metresOutside) {
        nearest = position;
      }
    }
    return nearest;
  }

  Future<PunchReceipt> submit(
    PunchPreparation preparation,
    Uint8List selfie, {
    DateTime? punchedAt,
  }) async {
    final session = _ref.read(sessionProvider);
    if (session == null || session.user.id <= 0)
      throw const ApiUnauthenticated();
    final coordinates = preparation.coordinates;
    if (coordinates == null || !preparation.canSubmit) {
      throw const ApiUnknown('A current GPS fix is required.');
    }
    final at = (punchedAt ?? DateTime.now()).toUtc();
    final queue = _ref.read(punchQueueProvider);
    final recent = await queue.recent(punchQueueAccount(session));
    final latest = recent
        .where((punch) => punch.state != PunchSyncState.rejected)
        .firstOrNull;
    if (latest != null &&
        at.difference(latest.at) < const Duration(minutes: 3)) {
      throw const ApiUnknown('Wait at least three minutes between punches.');
    }
    final deviceId = await _ref.read(punchDeviceProvider).read();
    return _ref
        .read(punchSyncProvider)
        .record(
          session,
          QueuedPunch(
            uuid: const Uuid().v4(),
            isClockingIn: preparation.isClockingIn,
            at: at,
            deviceId: deviceId,
            latitude: coordinates.latitude,
            longitude: coordinates.longitude,
            selfie: selfie,
          ),
        );
  }
}

final punchControllerProvider = Provider<PunchController>(PunchController.new);
