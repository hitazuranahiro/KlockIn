// Modified for KlockIN by Tomeku, 2026-11-25.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/scope.dart';
import '../../../core/theme/platform_chrome.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/glass_surface.dart';
import '../../../shared/widgets/klockin_mark.dart';
import '../../../shared/widgets/pressable.dart';
import '../../../shared/widgets/error_state_card.dart';
import '../../announcements/ui/announcements_screen.dart';
import '../../punch/ui/punch_screen.dart';
import '../../punch/ui/attendance_sync_card.dart';
import '../../punch/data/punch_queue.dart';
import '../../punch/data/punch_sync.dart';
import '../../../core/auth/session.dart';
import '../data/confirmed_work_snapshot.dart';
import '../data/confirmed_work_store.dart';
import '../data/home_api.dart';
import '../../approvals/data/approval_models.dart';
import '../../approvals/data/approvals_controller.dart';
import '../data/home_models.dart';
import 'break_card.dart';
import 'home_sections.dart';
import 'live_clock.dart';
import 'punch_card.dart';

final homeClockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final home = ref.watch(homeProvider);
    final session = supportsOfflinePunches ? ref.watch(sessionProvider) : null;
    final error = home.error;
    final hasNetwork = session == null
        ? null
        : ref.watch(punchConnectivityProvider).value;
    if (session != null) {
      ref.listen(punchConnectivityProvider, (previous, current) {
        if (previous?.value == false && current.value == true) {
          ref.invalidate(homeProvider);
        }
      });
    }
    final offline =
        session != null &&
        (hasNetwork == false ||
            error is ApiNetwork ||
            error is ApiTimeout ||
            error is ApiServer);

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: RefreshIndicator(
        color: AppColors.brandStrong,
        onRefresh: () async => ref.refresh(homeProvider.future),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 580),
            child: offline ? const _OfflineAttendance() : _body(ref, home),
          ),
        ),
      ),
    );
  }

  /// Explicit branching rather than [AsyncValue.when].
  ///
  /// Riverpod 3 reports a failed *first* load as `AsyncLoading` carrying an
  /// error, not as `AsyncError` -- so a `when(loading:)` branch swallows the
  /// failure and shows a skeleton that never resolves. Deciding on
  /// `value`/`hasError` directly says what this screen actually means:
  ///
  ///   data present  -> show it, even mid-refresh, so a pull-to-refresh
  ///                    never blanks the screen
  ///   error, no data -> explain it, and offer a way out
  ///   neither        -> genuine first load, so skeletons
  Widget _body(WidgetRef ref, AsyncValue<HomeData> home) {
    final data = home.value;
    if (data != null) return _HomeBody(key: ValueKey(data.user.id), data: data);

    final error = home.error;
    if (error != null) {
      return ErrorStateCard(
        failure: error is ApiFailure ? error : const ApiUnknown(),
        onRetry: () => ref.invalidate(homeProvider),
      );
    }

    return const _HomeSkeleton();
  }
}

class _OfflineAttendance extends ConsumerWidget {
  const _OfflineAttendance();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final snapshot = session != null && session.user.id > 0
        ? ref.watch(confirmedWorkProvider(punchQueueAccount(session))).value
        : null;
    final recent = ref.watch(recentPunchesProvider);
    final latest = recent.value
        ?.where((punch) => punch.state != PunchSyncState.rejected)
        .firstOrNull;

    Future<void> openPunch(bool isClockingIn) async {
      final policy = session == null || session.user.id <= 0
          ? null
          : await ref.read(
              cachedGeofenceProvider(punchQueueAccount(session)).future,
            );
      if (!context.mounted || !identical(session, ref.read(sessionProvider))) {
        return;
      }
      context.push(
        '/punch',
        extra: PunchArgs(
          isClockingIn: isClockingIn,
          geofence: policy ?? GeofenceState.unknown,
          clockInTime: latest != null && latest.isClockingIn
              ? DateFormat.Hm().format(latest.displayedAt.toLocal())
              : null,
        ),
      );
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      children: [
        _HomeAppBar(name: session?.user.fullName ?? '', unread: 0),
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.screen,
            AppSpace.x6,
            AppSpace.screen,
            AppSpace.scrollBottom,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ShiftClock(
                clock: ref.watch(homeClockProvider),
                status: latest == null
                    ? 'Offline'
                    : latest.isClockingIn
                    ? 'On the clock · offline'
                    : 'Clocked out · offline',
                statusColor: const Color(0xFFFFDA8C),
                action: ClockAction(
                  clockingIn: latest?.isClockingIn != true,
                  onPressed: () => openPunch(latest?.isClockingIn != true),
                ),
              ),
              const SizedBox(height: AppSpace.x12),
              Text(
                'Punches stay on this device until the server is reachable.',
                style: AppText.body.copyWith(color: AppColors.ink2),
              ),
              const SizedBox(height: AppSpace.x6),
              Text(
                'Connect to the internet to start or end a break.',
                style: AppText.body.copyWith(color: AppColors.ink2),
              ),
              if (latest == null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(
                    onPressed: () => openPunch(false),
                    child: const Text('Clock out'),
                  ),
                ),
              const SizedBox(height: AppSpace.x16),
              GlassSurface(
                radius: AppRadii.hero,
                padding: const EdgeInsets.all(AppSpace.x16),
                child: _OfflineWorkedHours(snapshot: snapshot),
              ),
              const AttendanceSyncCard(),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  onPressed: () => ref.invalidate(homeProvider),
                  child: const Text('Reconnect'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _OfflineWorkedHours extends ConsumerStatefulWidget {
  const _OfflineWorkedHours({required this.snapshot});

  final ConfirmedWorkSnapshot? snapshot;

  @override
  ConsumerState<_OfflineWorkedHours> createState() =>
      _OfflineWorkedHoursState();
}

class _OfflineWorkedHoursState extends ConsumerState<_OfflineWorkedHours>
    with WidgetsBindingObserver {
  Timer? _expiry;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _scheduleExpiry();
  }

  @override
  void didUpdateWidget(_OfflineWorkedHours oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.snapshot != widget.snapshot) _scheduleExpiry();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    _scheduleExpiry();
    setState(() {});
  }

  void _scheduleExpiry() {
    _expiry?.cancel();
    final snapshot = widget.snapshot;
    final now = ref.read(homeClockProvider)();
    if (snapshot != null && snapshot.isCurrentAt(now)) {
      _expiry = Timer(snapshot.workdayEndsAt.difference(now), () {
        if (!mounted) return;
        _scheduleExpiry();
        setState(() {});
      });
    }
  }

  @override
  void dispose() {
    _expiry?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = widget.snapshot;
    if (snapshot == null ||
        !snapshot.isCurrentAt(ref.watch(homeClockProvider)())) {
      return const Text(
        'Confirmed worked hours are unavailable for this workday.',
      );
    }
    final asOf = DateFormat('d MMM yyyy, HH:mm')
        .format(snapshot.confirmedAtSiteTime);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Last confirmed worked hours', style: AppText.cardTitle),
        const SizedBox(height: 4),
        Text(formatHms(snapshot.workedSeconds), style: AppText.heroNumber),
        Text('Workday ${snapshot.workday}', style: AppText.meta),
        Text('As of $asOf · ${snapshot.timeZone}', style: AppText.meta),
      ],
    );
  }
}

class _HomeBody extends ConsumerStatefulWidget {
  const _HomeBody({super.key, required this.data});

  final HomeData data;

  @override
  ConsumerState<_HomeBody> createState() => _HomeBodyState();
}

class _HomeBodyState extends ConsumerState<_HomeBody>
    with WidgetsBindingObserver {
  Timer? _breakRefresh;
  BreakPolicy? _latestBreakAction;
  String? _breakError;
  bool _savingBreak = false;
  bool _visible = true;

  BreakPolicy? get _breakPolicy {
    final action = _latestBreakAction;
    final policy = widget.data.breakPolicy;
    if (action != null &&
        (policy == null || action.asOf.isAfter(policy.asOf))) {
      return action;
    }
    return policy;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final visible = TickerMode.valuesOf(context).enabled;
    if (visible && !_visible) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _visible) _refreshBreakStatus();
      });
    }
    _visible = visible;
    _scheduleBreakRefresh();
  }

  @override
  void didUpdateWidget(_HomeBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    _scheduleBreakRefresh();
  }

  bool get _hasBreaks =>
      supportsOfflinePunches &&
      (_breakPolicy?.enabled == true || _breakPolicy?.isActive == true);

  void _scheduleBreakRefresh() {
    final state = WidgetsBinding.instance.lifecycleState;
    if (!_hasBreaks ||
        !_visible ||
        (state != null && state != AppLifecycleState.resumed)) {
      _breakRefresh?.cancel();
      _breakRefresh = null;
      return;
    }
    _breakRefresh ??= Timer.periodic(const Duration(seconds: 45), (_) {
      _refreshBreakStatus();
    });
  }

  void _refreshBreakStatus() {
    if (_hasBreaks && !_savingBreak && !ref.read(homeProvider).isLoading) {
      ref.invalidate(homeProvider);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _scheduleBreakRefresh();
    if (_visible && state == AppLifecycleState.resumed) _refreshBreakStatus();
  }

  @override
  void dispose() {
    _breakRefresh?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _changeBreak(BreakAction action) async {
    if (_savingBreak) return;
    setState(() {
      _savingBreak = true;
      _breakError = null;
    });
    try {
      final policy = await ref.read(homeApiProvider).changeBreak(action);
      if (mounted) setState(() => _latestBreakAction = policy);
    } on ApiFailure catch (failure) {
      if (mounted) {
        setState(() {
          _breakError = switch (failure) {
            ApiNetwork() || ApiTimeout() =>
              'Couldn’t confirm your break. Check your connection and refresh.',
            _ => failure.message,
          };
        });
      }
    } finally {
      if (mounted) {
        setState(() => _savingBreak = false);
        _scheduleBreakRefresh();
        ref.invalidate(homeProvider);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.data;
    final recent = supportsOfflinePunches
        ? ref.watch(recentPunchesProvider).value
        : null;
    final local = recent
        ?.where(
          (punch) =>
              punch.state != PunchSyncState.rejected &&
              (data.punch.lastActivityAt == null ||
                  punch.at.isAfter(data.punch.lastActivityAt!)),
        )
        .firstOrNull;
    final punch = local == null
        ? data.punch
        : PunchState(
            isClockedIn: local.isClockingIn,
            clockInTime: local.isClockingIn
                ? DateFormat.Hm().format(local.displayedAt.toLocal())
                : data.punch.clockInTime,
            lastActivityAt: local.at,
          );
    final policy = _breakPolicy;
    final clock = ref.watch(homeClockProvider);
    final showBreakAction = punch.isClockedIn || policy?.isActive == true;
    final showBreakCard =
        supportsOfflinePunches &&
        policy != null &&
        (policy.isActive ||
            (policy.enabled && (punch.isClockedIn || policy.usedSeconds > 0)) ||
            (punch.isClockedIn && _breakError != null));
    final canStartBreak =
        policy?.enabled == true &&
        policy?.canStart == true &&
        punch.isClockedIn &&
        data.punch.isClockedIn;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      children: [
        _HomeAppBar(name: data.user.fullName, unread: data.unreadNotifications),
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.screen,
            AppSpace.x6,
            AppSpace.screen,
            AppSpace.scrollBottom,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              PunchCard(
                punch: punch,
                geofence: data.geofence,
                today: data.today,
                clock: clock,
                breakActive: policy?.isActive == true,
                showsBreakCard: showBreakCard,
                onPunch: !supportsOfflinePunches
                    ? null
                    : () => context.push(
                        '/punch',
                        extra: PunchArgs(
                          // Clocked in means the next action is out, and vice versa.
                          isClockingIn: !punch.isClockedIn,
                          geofence: data.geofence,
                          today: data.today,
                          clockInTime: punch.clockInTime,
                        ),
                      ),
              ),

              if (showBreakCard) ...[
                const SizedBox(height: AppSpace.x12),
                BreakCard(
                  policy: policy,
                  clock: clock,
                  busy: _savingBreak,
                  showAction: showBreakAction,
                  onAction: policy.isActive
                      ? () => _changeBreak(BreakAction.end)
                      : canStartBreak
                      ? () => _changeBreak(BreakAction.start)
                      : null,
                  unavailableReason:
                      _breakError ??
                      (!showBreakAction || policy.isActive || canStartBreak
                          ? null
                          : !data.punch.isClockedIn
                          ? 'Sync your clock-in before starting a break.'
                          : policy.remainingSeconds == 0
                          ? 'You’ve used your break allowance.'
                          : 'A break is unavailable for this shift.'),
                ),
              ],

              const AttendanceSyncCard(),

              // Hidden at zero rather than telling every manager "0 requests
              // need you".
              if (data.capabilities.isManager)
                _ApprovalsBand(pendingApprovals: data.pendingApprovals),

              const SizedBox(height: AppSpace.x20),
              Text(
                'Work tools',
                style: AppText.cardTitle.copyWith(fontSize: 17),
              ),
              const SizedBox(height: AppSpace.x8),
              QuickActions(
                actions: [
                  if (Modules.leave) ...[
                    QuickAction(
                      icon: Icons.event_available_outlined,
                      label: 'Request time off',
                      onTap: () => context.go('/time/leave/apply'),
                    ),
                    QuickAction(
                      icon: Icons.event_note_outlined,
                      label: 'Leave balance',
                      onTap: () => context.go('/time/leave'),
                    ),
                  ],
                  if (Modules.attendance)
                    QuickAction(
                      icon: Icons.history_rounded,
                      label: 'Time records',
                      onTap: () => context.go('/time'),
                    ),
                  if (Modules.employee)
                    QuickAction(
                      icon: Icons.group_outlined,
                      label: 'People directory',
                      onTap: () => context.go('/team/directory'),
                    ),
                  if (Modules.payroll)
                    QuickAction(
                      icon: Icons.receipt_long_outlined,
                      label: 'Payslips',
                      onTap: () => context.go('/requests/payslips'),
                    ),
                  if (Modules.requests)
                    QuickAction(
                      icon: Icons.inbox_outlined,
                      label: 'Work requests',
                      onTap: () => context.go('/requests'),
                    ),
                ],
              ),

              if (data.onLeaveToday.isNotEmpty) ...[
                const SizedBox(height: AppSpace.x16),
                OnLeaveToday(
                  colleagues: data.onLeaveToday,
                  onTap: () => context.go('/team'),
                ),
              ],

              if (data.announcement != null) ...[
                const SizedBox(height: AppSpace.x12),
                AnnouncementCard(
                  announcement: data.announcement!,
                  onTap: () =>
                      openAnnouncement(context, ref, data.announcement!.id),
                  onSeeAll: () => context.push('/home/announcements'),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _HomeAppBar extends StatelessWidget {
  const _HomeAppBar({required this.name, required this.unread});

  final String name;
  final int unread;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: PlatformChrome.appBarPaddingOf(context)
          .copyWith(left: AppSpace.screen, right: AppSpace.screen),
      child: Row(
        children: [
          const KlockInMarkTile(),
          const SizedBox(width: AppSpace.x12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Today',
                  style: AppText.appBarTitle.copyWith(fontSize: 29),
                ),
                if (name.isNotEmpty) Text(name, style: AppText.meta),
              ],
            ),
          ),
          _NotificationBell(unread: unread),
          const SizedBox(width: AppSpace.x4),
          Semantics(
            button: true,
            label: 'Your profile',
            excludeSemantics: true,
            onTap: () => context.go('/me'),
            child: Pressable(
              onTap: () => context.go('/me'),
              child: SizedBox(
                width: kMinHitTarget,
                height: kMinHitTarget,
                child: Center(child: _BrandAvatar(name: name)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BrandAvatar extends StatelessWidget {
  const _BrandAvatar({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty);
    final initials = parts.isEmpty
        ? '?'
        : parts.length == 1
        ? parts.first.characters.first.toUpperCase()
        : (parts.first.characters.first + parts.last.characters.first)
              .toUpperCase();
    return Container(
      width: 38,
      height: 38,
      decoration: const BoxDecoration(
        color: AppColors.brandTint,
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(
        initials,
        style: AppText.cardTitle.copyWith(
          fontSize: 13,
          fontWeight: FontWeight.w800,
          color: AppColors.brandTintInk,
        ),
      ),
    );
  }
}

class _NotificationBell extends StatelessWidget {
  const _NotificationBell({required this.unread});

  final int unread;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: unread > 0 ? 'Notifications, $unread unread' : 'Notifications',
      excludeSemantics: true,
      onTap: () => context.go('/home/notifications'),
      child: Pressable(
        onTap: () => context.go('/home/notifications'),
        child: SizedBox(
          width: kMinHitTarget,
          height: kMinHitTarget,
          child: Center(
            child: Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: AppColors.surface.withValues(alpha: 0.82),
                shape: BoxShape.circle,
                border: Border.all(color: AppColors.line),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  const Icon(
                    Icons.notifications_none,
                    size: 19,
                    color: AppColors.ink,
                  ),
                  if (unread > 0)
                    Positioned(
                      top: 8,
                      right: 9,
                      child: Container(
                        width: 7,
                        height: 7,
                        decoration: BoxDecoration(
                          color: AppColors.brand,
                          shape: BoxShape.circle,
                          border: Border.all(color: AppColors.bg, width: 1.5),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeSkeleton extends StatelessWidget {
  const _HomeSkeleton();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpace.screen,
        AppSpace.x28,
        AppSpace.screen,
        AppSpace.scrollBottom,
      ),
      children: const [
        SkeletonBar(width: 100, height: 42),
        SizedBox(height: AppSpace.x16),
        AppCard.skeleton(height: 208),
        SizedBox(height: AppSpace.x16),
        AppCard.skeleton(height: 128),
      ],
    );
  }
}

class _ApprovalsBand extends ConsumerWidget {
  const _ApprovalsBand({required this.pendingApprovals});

  /// From the home aggregate. When present this band costs nothing extra --
  /// no six-source, up-to-thirty-request fetch just to show a count.
  final PendingApprovals? pendingApprovals;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fromServer = pendingApprovals;
    if (fromServer != null) {
      if (fromServer.total == 0) return const SizedBox.shrink();
      return _band(
        context,
        count: fromServer.total,
        subtitle: fromServer.summary(),
      );
    }

    // A server before PR #3407 has no pending_approvals field at all --
    // fall back to counting the full inbox client-side, as this always did.
    final inbox = ref.watch(approvalsProvider).value;
    if (inbox == null || inbox.items.isEmpty) return const SizedBox.shrink();
    return _band(context, count: inbox.items.length, subtitle: inbox.summary());
  }

  Widget _band(
    BuildContext context, {
    required int count,
    required String subtitle,
  }) => Padding(
    padding: const EdgeInsets.only(top: AppSpace.x14),
    child: RoleBand(
      count: count,
      subtitle: subtitle,
      onTap: () => context.go('/team/approvals'),
    ),
  );
}
