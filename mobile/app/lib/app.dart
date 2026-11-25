// Modified for KlockIN by Tomeku, 2026-11-25.
import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/auth/biometric_lock.dart';
import 'core/auth/session.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';
import 'core/theme/tokens.dart';
import 'features/punch/data/punch_queue.dart';
import 'features/punch/data/punch_sync.dart';
import 'l10n/app_localizations.dart';
import 'shared/widgets/klockin_mark.dart';
import 'shared/widgets/toast.dart';

/// Restores any stored session before the first frame.
///
/// Reads local storage only, so this resolves in milliseconds and works
/// offline. Whether the token is still *valid* is settled by the first real
/// request, not here.
final sessionRestoreProvider = FutureProvider<void>((ref) async {
  await ref.read(sessionProvider.notifier).restore();
  await ref.read(biometricEnabledProvider.notifier).restore();
});

class KlockInApp extends ConsumerWidget {
  const KlockInApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final restore = ref.watch(sessionRestoreProvider);

    return restore.when(
      loading: () => const _Splash(),
      // A failed restore is not fatal: it means no usable session, which is
      // the same situation as a first launch.
      error: (_, _) => const _AppRouter(),
      data: (_) => const _AppRouter(),
    );
  }
}

class _AppRouter extends ConsumerStatefulWidget {
  const _AppRouter();

  @override
  ConsumerState<_AppRouter> createState() => _AppRouterState();
}

class _AppRouterState extends ConsumerState<_AppRouter>
    with WidgetsBindingObserver {
  /// Bridges Riverpod's session state to go_router's refreshListenable.
  final _sessionChanged = ValueNotifier<int>(0);
  late final _router = buildRouter(
    initialLocation: ref.read(sessionProvider) == null ? '/signin' : '/home',
    isSignedIn: () => ref.read(sessionProvider) != null,
    refreshOn: _sessionChanged,
  );

  StreamSubscription<List<ConnectivityResult>>? _network;
  Timer? _retry;

  @override
  void initState() {
    super.initState();
    if (!supportsOfflinePunches) return;
    WidgetsBinding.instance.addObserver(this);
    _network = Connectivity().onConnectivityChanged.listen((_) => _sync());
    _retry = Timer.periodic(const Duration(minutes: 1), (_) => _sync());
    WidgetsBinding.instance.addPostFrameCallback((_) => _sync());
  }

  void _sync() {
    if (mounted && ref.read(sessionProvider) != null) {
      unawaited(ref.read(punchSyncProvider).flush());
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !mounted) return;
    // An operating-system background task can commit receipts in another
    // isolate without invalidating the foreground providers.
    ref.invalidate(recentPunchesProvider);
    ref.invalidate(pendingPunchCountProvider);
    ref.invalidate(lastSuccessfulPunchSyncProvider);
    _sync();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _retry?.cancel();
    unawaited(_network?.cancel());
    _sessionChanged.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(sessionProvider, (_, _) {
      _sessionChanged.value++;
      if (supportsOfflinePunches) _sync();
    });

    return MaterialApp.router(
      onGenerateTitle: (context) => AppL10n.of(context).appTitle,
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      localizationsDelegates: const [
        AppL10n.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppL10n.supportedLocales,
      routerConfig: _router,
      // One host for the whole app, so a toast raised on one screen survives
      // the navigation that usually follows it. The biometric gate sits
      // outside the toast host, so a lock screen is never seen carrying a
      // stray toast meant for whatever was open before.
      builder: (context, child) =>
          BiometricGate(child: ToastHost(child: child!)),
    );
  }
}

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        // Light, like the v2 sign-in it hands over to.
        backgroundColor: AppColors.surface,
        body: Center(child: KlockInMark(size: 72)),
      ),
    );
  }
}
