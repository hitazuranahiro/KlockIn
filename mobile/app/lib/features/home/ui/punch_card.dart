import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/glass_surface.dart';
import '../data/home_models.dart';
import 'live_clock.dart';

class PunchCard extends StatelessWidget {
  const PunchCard({
    super.key,
    required this.punch,
    required this.geofence,
    required this.today,
    required this.clock,
    this.onPunch,
  });

  final PunchState punch;
  final GeofenceState geofence;
  final TodayTotals today;
  final DateTime Function() clock;
  final VoidCallback? onPunch;

  @override
  Widget build(BuildContext context) {
    final clockedIn = punch.isClockedIn;
    final state = clockedIn
        ? 'On the clock'
        : punch.clockInTime != null
        ? 'Clocked out'
        : 'Shift not started';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ShiftClock(
          clock: clock,
          status: state,
          statusColor: clockedIn
              ? const Color(0xFFAAFFD3)
              : const Color(0xFFCFDEFF),
          action: onPunch == null
              ? null
              : ClockAction(clockingIn: !clockedIn, onPressed: onPunch),
        ),
        if (geofence.enabled)
          const Padding(
            padding: EdgeInsets.only(top: AppSpace.x12),
            child: _LocationNote(),
          ),
        const SizedBox(height: AppSpace.x16),
        GlassSurface(
          radius: AppRadii.hero,
          padding: const EdgeInsets.all(AppSpace.x16),
          child: WorkedTicker(
            workedAtFetch: today.workedSeconds,
            running: clockedIn,
            builder: (context, worked) {
              final shift = today.shiftSeconds;
              return _ShiftActivity(
                worked: worked,
                clockIn: punch.clockInTime,
                latest: punch.lastActivityAt,
                breakTime: formatShort(
                  TodayTotals.secondsOf(today.breakTime) ?? 0,
                ),
                overtime: formatShort(
                  TodayTotals.secondsOf(today.overtime) ?? 0,
                ),
                remaining: clockedIn && shift != null && worked < shift
                    ? '${formatHm(shift - worked)} left in shift'
                    : null,
              );
            },
          ),
        ),
      ],
    );
  }
}

class ShiftClock extends StatelessWidget {
  const ShiftClock({
    super.key,
    required this.clock,
    required this.status,
    required this.statusColor,
    this.action,
  });

  final DateTime Function() clock;
  final String status;
  final Color statusColor;
  final Widget? action;

  static const _navy = Color(0xFF093477);

  @override
  Widget build(BuildContext context) {
    final highContrast = MediaQuery.highContrastOf(context);
    final radius = BorderRadius.circular(AppRadii.hero);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: radius,
        boxShadow: highContrast
            ? null
            : const [
                BoxShadow(
                  color: Color(0x40104FCE),
                  blurRadius: 24,
                  spreadRadius: -7,
                  offset: Offset(0, 11),
                ),
              ],
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: _navy,
            gradient: highContrast
                ? null
                : const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [Color(0xFF104298), Color(0xFF124FBF), _navy],
                    stops: [0, 0.51, 1],
                  ),
          ),
          child: Stack(
            children: [
              if (!highContrast)
                const Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: RadialGradient(
                        center: Alignment(1.0, -1.2),
                        radius: 1.2,
                        colors: [Color(0x6071B5FF), Color(0x0071B5FF)],
                      ),
                    ),
                  ),
                ),
              DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: radius,
                  border: Border.all(
                    color: highContrast
                        ? Colors.white
                        : const Color(0x54FFFFFF),
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(AppSpace.x18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      WallClock(
                        clock: clock,
                        builder: (context, now) {
                          final date = DateFormat.MMMEd().format(now);
                          final time = DateFormat.Hm().format(now);
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Wrap(
                                alignment: WrapAlignment.spaceBetween,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                spacing: AppSpace.x8,
                                runSpacing: AppSpace.x8,
                                children: [
                                  Text(
                                    date,
                                    style: AppText.body.copyWith(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  _ClockStatus(
                                    label: status,
                                    color: statusColor,
                                  ),
                                ],
                              ),
                              const SizedBox(height: AppSpace.x16),
                              Semantics(
                                label: 'Local time $time',
                                excludeSemantics: true,
                                child: FittedBox(
                                  fit: BoxFit.scaleDown,
                                  child: Text(
                                    time,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 66,
                                      fontWeight: FontWeight.w600,
                                      letterSpacing: -3.6,
                                      height: 1.06,
                                      fontFeatures: [
                                        FontFeature.tabularFigures(),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          );
                        },
                      ),
                      if (action != null) ...[
                        const SizedBox(height: AppSpace.x16),
                        action!,
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ClockStatus extends StatelessWidget {
  const _ClockStatus({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0x3409245E),
        border: Border.all(color: const Color(0x46FFFFFF)),
        borderRadius: BorderRadius.circular(AppRadii.pill),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpace.x10,
          vertical: AppSpace.x6,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: const SizedBox.square(dimension: 7),
            ),
            const SizedBox(width: AppSpace.x6),
            Flexible(
              child: Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  height: 1.3,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ClockAction extends StatelessWidget {
  const ClockAction({
    super.key,
    required this.clockingIn,
    required this.onPressed,
  });

  final bool clockingIn;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 54),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        backgroundColor: const Color(0xFF1760DB),
        foregroundColor: Colors.white,
        side: BorderSide(
          color: MediaQuery.highContrastOf(context)
              ? Colors.white
              : const Color(0x707EB6FF),
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(17)),
        textStyle: Theme.of(context).textTheme.labelLarge
            ?.copyWith(fontSize: 16, fontWeight: FontWeight.w700),
      ),
      icon: Icon(
        clockingIn ? Icons.login_rounded : Icons.logout_rounded,
        size: 20,
      ),
      label: Text(clockingIn ? 'Clock in' : 'Clock out'),
    );
  }
}

class _LocationNote extends StatelessWidget {
  const _LocationNote();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(
          Icons.location_on_outlined,
          size: 17,
          color: AppColors.brandStrong,
        ),
        const SizedBox(width: AppSpace.x6),
        Flexible(
          child: Text('Worksite location required', style: AppText.meta),
        ),
      ],
    );
  }
}

class _ShiftActivity extends StatelessWidget {
  const _ShiftActivity({
    required this.worked,
    required this.clockIn,
    required this.latest,
    required this.breakTime,
    required this.overtime,
    required this.remaining,
  });

  final int worked;
  final String? clockIn;
  final DateTime? latest;
  final String breakTime;
  final String overtime;
  final String? remaining;

  @override
  Widget build(BuildContext context) {
    final lastTime = latest == null
        ? null
        : DateFormat.Hm().format(latest!.toLocal());
    final workedMetric = _ShiftMetric(
      label: 'Worked today',
      value: formatHms(worked),
    );
    final clockInMetric = _ShiftMetric(
      label: 'First clock-in',
      value: clockIn ?? '—',
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Shift activity',
          style: AppText.cardTitle.copyWith(fontSize: 17, color: AppColors.ink),
        ),
        const SizedBox(height: AppSpace.x12),
        LayoutBuilder(
          builder: (context, constraints) {
            final minWidth = 270 * MediaQuery.textScalerOf(context).scale(1);
            if (constraints.maxWidth < minWidth) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  workedMetric,
                  const SizedBox(height: AppSpace.x10),
                  clockInMetric,
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: workedMetric),
                const SizedBox(width: AppSpace.x12),
                Expanded(child: clockInMetric),
              ],
            );
          },
        ),
        if (remaining != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpace.x6),
            child: Text(remaining!, style: AppText.meta),
          ),
        const SizedBox(height: AppSpace.x12),
        const Divider(height: 1, color: AppColors.line),
        const SizedBox(height: AppSpace.x10),
        Wrap(
          spacing: AppSpace.x16,
          runSpacing: AppSpace.x8,
          children: [
            Text('Break $breakTime', style: AppText.meta),
            Text('Overtime $overtime', style: AppText.meta),
            if (lastTime != null && lastTime != clockIn)
              Text('Last activity · $lastTime local time', style: AppText.meta),
          ],
        ),
      ],
    );
  }
}

class _ShiftMetric extends StatelessWidget {
  const _ShiftMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: AppText.meta.copyWith(fontWeight: FontWeight.w600)),
        const SizedBox(height: AppSpace.x4),
        Text(
          value,
          style: const TextStyle(
            color: AppColors.ink,
            fontSize: 23,
            height: 1.12,
            fontWeight: FontWeight.w700,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}
