// Modified for KlockIN by Tomeku, 2026-11-25.
/// Preparing a punch: whether the button is live, and why not.
///
/// The location service is faked, which is the whole reason it sits behind an
/// interface. Everything below -- permissions, GPS, the platform prompt --
/// cannot be exercised without a device; everything above it can, and this is
/// the part that decides whether someone is allowed to clock in.
library;

import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/core/api/api_failure.dart';
import 'package:klockin/features/home/data/home_models.dart';
import 'package:klockin/features/punch/data/location_service.dart';
import 'package:klockin/features/punch/data/punch_controller.dart';

class FakeLocation implements LocationService {
  FakeLocation.at(this._coordinates) : _failure = null;
  FakeLocation.failing(this._failure) : _coordinates = null;

  final Coordinates? _coordinates;
  final LocationFailure? _failure;
  int calls = 0;

  @override
  Future<Coordinates> current() async {
    calls++;
    if (_failure != null) throw _failure;
    return _coordinates!;
  }
}

const _office = GeofenceState(
  enabled: true,
  latitude: 12.9716,
  longitude: 77.5946,
  radiusInMeters: 150,
);

Future<PunchPreparation> prepare({
  required LocationService location,
  GeofenceState geofence = _office,
  bool isClockingIn = true,
}) async {
  final container = ProviderContainer(
    overrides: [locationServiceProvider.overrideWithValue(location)],
  );
  addTearDown(container.dispose);

  return container
      .read(punchControllerProvider)
      .prepare(isClockingIn: isClockingIn, geofence: geofence);
}

void main() {
  test('inside the fence, the punch is allowed', () async {
    final preparation = await prepare(
      location: FakeLocation.at(
        const Coordinates(latitude: 12.9716, longitude: 77.5946),
      ),
    );

    expect(preparation.canSubmit, isTrue);
    expect(preparation.blockedReason, isNull);
    expect(preparation.fence!.isInside, isTrue);
  });

  test('outside the fence, the punch is refused before it is sent', () async {
    // Better to say no here than to let the server say no after a round trip.
    final preparation = await prepare(
      location: FakeLocation.at(
        const Coordinates(latitude: 9.9312, longitude: 76.2673),
      ),
    );

    expect(preparation.canSubmit, isFalse);
    expect(
      preparation.blockedReason,
      contains('outside the nearest allowed work location'),
    );
  });

  test('the refusal says which way the punch was going', () async {
    final out = await prepare(
      location: FakeLocation.at(
        const Coordinates(latitude: 9.9312, longitude: 76.2673),
      ),
      isClockingIn: false,
    );
    expect(out.blockedReason, contains('clock out'));
  });

  test('GPS is captured even when no fence is configured', () async {
    final location = FakeLocation.at(
      const Coordinates(latitude: 0, longitude: 0),
    );

    final preparation = await prepare(
      location: location,
      geofence: const GeofenceState(enabled: false),
    );

    expect(location.calls, 1);
    expect(preparation.canSubmit, isTrue);
    expect(preparation.coordinates, isNotNull);
    expect(preparation.fence, isNull);
  });

  test(
    'an alternate allowed location can accept a punch outside the primary one',
    () async {
      final policy = GeofenceState.fromJson({
        'enabled': true,
        'latitude': 12.9716,
        'longitude': 77.5946,
        'radius_in_meters': 100,
        'locations': [
          {
            'latitude': 12.9716,
            'longitude': 77.5946,
            'radius_in_meters': 100,
            'name': 'Main',
          },
          {
            'latitude': 14.5,
            'longitude': 121.0,
            'radius_in_meters': 50,
            'name': 'Field Office',
          },
        ],
      });
      final preparation = await prepare(
        geofence: GeofenceState.fromJson(policy.toJson()),
        location: FakeLocation.at(
          const Coordinates(latitude: 14.5, longitude: 121.0),
        ),
      );
      expect(preparation.canSubmit, isTrue);
      expect(preparation.fence?.siteName, 'Field Office');
      expect(preparation.locationCheckPending, isFalse);
    },
  );

  test(
    'unknown offline policy queues a GPS fix with a pending location check',
    () async {
      final preparation = await prepare(
        geofence: GeofenceState.unknown,
        location: FakeLocation.at(
          const Coordinates(latitude: 14.5, longitude: 121.0),
        ),
      );
      expect(preparation.canSubmit, isTrue);
      expect(preparation.locationCheckPending, isTrue);
      expect(preparation.coordinates, isNotNull);
    },
  );

  group('location failures each block, with their own words', () {
    test('permission denied can be retried', () async {
      final preparation = await prepare(
        location: FakeLocation.failing(
          const LocationFailure(
            LocationProblem.denied,
            'Your workplace requires your location to clock in.',
          ),
        ),
      );

      expect(preparation.canSubmit, isFalse);
      expect(preparation.blockedReason, contains('requires your location'));
      expect(preparation.locationFailure!.isRetryable, isTrue);
    });

    test(
      'permanently denied points at Settings instead of asking again',
      () async {
        final preparation = await prepare(
          location: FakeLocation.failing(
            const LocationFailure(
              LocationProblem.deniedForever,
              'Location access is blocked for this app. Allow it in Settings '
              'to clock in.',
            ),
          ),
        );

        expect(preparation.locationFailure!.isRetryable, isFalse);
        expect(preparation.blockedReason, contains('Settings'));
      },
    );

    test('location switched off device-wide is its own message', () async {
      final preparation = await prepare(
        location: FakeLocation.failing(
          const LocationFailure(
            LocationProblem.servicesDisabled,
            'Location is switched off on this device. Turn it on to clock in.',
          ),
        ),
      );

      expect(preparation.canSubmit, isFalse);
      expect(preparation.blockedReason, contains('switched off'));
    });

    test('no fix available is not mistaken for a refusal', () async {
      final preparation = await prepare(
        location: FakeLocation.failing(
          const LocationFailure(
            LocationProblem.unavailable,
            'Could not get your location. Try again somewhere with a clearer '
            'signal.',
          ),
        ),
      );

      expect(preparation.locationFailure!.problem, LocationProblem.unavailable);
      expect(preparation.locationFailure!.isRetryable, isTrue);
    });
  });

  test('a fence with a nonsense radius does not lock everyone out', () async {
    // A misconfigured radius must not become a fence nobody can be inside.
    final preparation = await prepare(
      location: FakeLocation.at(
        const Coordinates(latitude: 12.9716, longitude: 77.5946),
      ),
      geofence: const GeofenceState(
        enabled: true,
        latitude: 12.9716,
        longitude: 77.5946,
        radiusInMeters: 0,
      ),
    );

    expect(preparation.fence, isNull);
    expect(preparation.canSubmit, isTrue);
  });

  test('an unauthenticated user cannot queue a punch', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    await expectLater(
      container
          .read(punchControllerProvider)
          .submit(const PunchPreparation(isClockingIn: true), Uint8List(1)),
      throwsA(isA<ApiUnauthenticated>()),
    );
  });
}
