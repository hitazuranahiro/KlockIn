// Modified for KlockIN by Tomeku, 2026-11-25.
/// Session state, and the providers that hang off it.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/data/auth_api.dart';
import '../../features/auth/data/auth_models.dart';
import '../../features/punch/data/punch_device.dart';
import '../api/api_client.dart';
import '../api/api_failure.dart';
import '../api/host.dart';
import 'profile_store.dart';
import 'session_lock.dart';
import 'token_store.dart';

/// Who is signed in, if anyone.
@immutable
class Session {
  const Session({
    required this.host,
    required this.user,
    required this.capabilities,
    required this.isCleartext,
    required this.geoFencingEnabled,
    required this.faceDetectionEnabled,
  });

  final String host;
  final SignedInUser user;
  final Capabilities capabilities;

  /// Surfaced in the UI so an unencrypted connection is never invisible.
  final bool isCleartext;

  final bool geoFencingEnabled;
  final bool faceDetectionEnabled;
}

final tokenStoreProvider = Provider<TokenStore>((ref) => TokenStore());

final sessionLockProvider = Provider<SessionLock>((ref) => makeSessionLock());

final profileStoreProvider = Provider<ProfileStore>((ref) => ProfileStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    tokenStore: ref.watch(tokenStoreProvider),
    sessionLock: ref.watch(sessionLockProvider),
    onSessionLost: () => ref.read(sessionProvider.notifier).expire(),
  );
});

final authApiProvider = Provider<AuthApi>(
  (ref) => AuthApi(ref.watch(apiClientProvider)),
);

final sessionProvider = NotifierProvider<SessionController, Session?>(
  SessionController.new,
);

class SessionController extends Notifier<Session?> {
  @override
  Session? build() => null;

  /// Probes the host before sending credentials and the installation ID.
  ///
  /// Persist tokens and the employee profile after successful authentication.
  Future<void> signIn({
    required String rawHost,
    String? username,
    String? employeeId,
    required String password,
  }) async {
    final normalised = normaliseHost(rawHost);
    if (!normalised.isValid) {
      throw ApiIncompatibleServer(normalised.error!);
    }
    final host = normalised.host;

    final api = ref.read(authApiProvider);
    await api.probe(host);

    final device = ref.read(punchDeviceProvider);
    final String? deviceId;
    try {
      deviceId = device.supportsBinding ? await device.read() : null;
    } on Exception {
      throw const ApiUnknown(
        'KlockIN could not identify this device. Reopen the app and try again.',
      );
    }
    final result = await api.signIn(
      host: host,
      username: username,
      employeeId: employeeId,
      password: password,
      deviceId: deviceId,
    );

    // The pre-flight catches a server that reports an old version, but one
    // that reports no version at all still reaches here. Credentials were
    // correct; the server simply cannot support the app. Nothing is stored,
    // so this leaves no half-session behind.
    if (!result.hasMobileApi) {
      throw const ApiIncompatibleServer(
        'The KlockIN server is missing required mobile account information. '
        'It needs updating before the app can use it.',
      );
    }

    final profile = StoredProfile(
      user: result.user,
      capabilities: result.capabilities,
      isCleartext: normalised.isCleartext,
      geoFencingEnabled: result.geoFencingEnabled,
      faceDetectionEnabled: result.faceDetectionEnabled,
    );
    await ref.read(sessionLockProvider).run(() async {
      await ref.read(profileStoreProvider).write(profile);
      await ref
          .read(tokenStoreProvider)
          .write(
            StoredSession(
              host: host,
              accessToken: result.accessToken,
              refreshToken: result.refreshToken,
              employeeId: result.user.id,
            ),
          );
      ref.read(apiClientProvider).useHost(host);
      state = _sessionFrom(host, profile);
    });
  }

  /// Restores a session from storage at launch.
  ///
  /// Reads only, no network: a returning user gets their app immediately and
  /// can open it with no connection. The token is what proves the session is
  /// real -- if it has expired or been revoked, the first request refreshes
  /// it or signs out, which is the interceptor's job rather than this one's.
  ///
  /// The host is taken from the *token* record, never from the profile, so a
  /// token can only ever be sent back to the server that issued it.
  Future<void> restore({bool attendanceOnly = false}) async {
    final stored = await ref.read(tokenStoreProvider).read();
    if (stored == null ||
        (!kDebugMode && !stored.host.startsWith('https://'))) {
      state = null;
      return;
    }

    ref.read(apiClientProvider).useHost(stored.host);

    if (attendanceOnly) {
      final employeeId = stored.employeeId;
      state = employeeId == null || employeeId <= 0
          ? null
          : Session(
              host: stored.host,
              user: SignedInUser(id: employeeId, fullName: ''),
              capabilities: Capabilities.empty,
              isCleartext: stored.host.startsWith('http://'),
              geoFencingEnabled: false,
              faceDetectionEnabled: false,
            );
      return;
    }

    final profile = await ref.read(profileStoreProvider).read();
    if (profile == null || profile.user.id != stored.employeeId) {
      // Token without a profile: still signed in, just nothing cached to
      // draw. Home fetches what it needs anyway.
      state = Session(
        host: stored.host,
        user: const SignedInUser(id: 0, fullName: ''),
        capabilities: Capabilities.empty,
        isCleartext: stored.host.startsWith('http://'),
        geoFencingEnabled: false,
        faceDetectionEnabled: false,
      );
      return;
    }

    state = _sessionFrom(stored.host, profile);
  }

  Session _sessionFrom(String host, StoredProfile profile) => Session(
    host: host,
    user: profile.user,
    capabilities: profile.capabilities,
    isCleartext: profile.isCleartext,
    geoFencingEnabled: profile.geoFencingEnabled,
    faceDetectionEnabled: profile.faceDetectionEnabled,
  );

  Future<void> signOut() async {
    await ref.read(sessionLockProvider).run(() async {
      await ref.read(tokenStoreProvider).clear();
      await ref.read(profileStoreProvider).clear();
      state = null;
    });
  }

  /// Called after the foreground interceptor has cleared the saved token.
  void expire() => state = null;
}
