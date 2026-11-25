import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'confirmed_work_snapshot.dart';
import 'home_models.dart';

class ConfirmedWorkStore {
  ConfirmedWorkStore({FlutterSecureStorage? storage})
    : _storage =
          storage ??
          const FlutterSecureStorage(
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.unlocked_this_device,
            ),
          );

  final FlutterSecureStorage _storage;
  Future<void> _writes = Future.value();

  String _key(String account) => 'klockin.confirmed-work.v1.$account';
  String _geofenceKey(String account) =>
      'klockin.work-location-policy.v1.$account';

  Future<ConfirmedWorkSnapshot?> read(String account) async {
    try {
      final value = await _storage.read(key: _key(account));
      if (value == null) return null;
      final body = jsonDecode(value);
      return body is Map<String, dynamic>
          ? ConfirmedWorkSnapshot.fromJson(body)
          : null;
    } on Exception {
      return null;
    }
  }

  Future<GeofenceState?> readGeofence(String account) async {
    try {
      final value = await _storage.read(key: _geofenceKey(account));
      final policy = value == null ? null : jsonDecode(value);
      return policy is Map<String, dynamic>
          ? GeofenceState.fromJson(policy)
          : null;
    } on Exception {
      return null;
    }
  }

  Future<void> saveGeofence(String account, GeofenceState policy) async {
    if (!policy.known) return;
    try {
      await _storage.write(
        key: _geofenceKey(account),
        value: jsonEncode(policy.toJson()),
      );
    } on Exception {
      // An unavailable keychain must not hide live Home data.
    }
  }

  Future<void> save(String account, ConfirmedWorkSnapshot snapshot) {
    // Reloads can finish out of order. Read and replace the cached value
    // serially so an older server response cannot undo a newer confirmation.
    return _writes = _writes.then((_) async {
      final existing = await read(account);
      if (existing != null &&
          existing.confirmedAt.isAfter(snapshot.confirmedAt)) {
        return;
      }
      try {
        await _storage.write(
          key: _key(account),
          value: jsonEncode(snapshot.toJson()),
        );
      } on Exception {
        // A cache write must not hide live server data.
      }
    });
  }
}

final confirmedWorkStoreProvider = Provider<ConfirmedWorkStore>(
  (ref) => ConfirmedWorkStore(),
);

final confirmedWorkProvider = FutureProvider.autoDispose
    .family<ConfirmedWorkSnapshot?, String>(
      (ref, account) => ref.watch(confirmedWorkStoreProvider).read(account),
    );

final cachedGeofenceProvider = FutureProvider.autoDispose
    .family<GeofenceState?, String>(
      (ref, account) =>
          ref.watch(confirmedWorkStoreProvider).readGeofence(account),
    );
