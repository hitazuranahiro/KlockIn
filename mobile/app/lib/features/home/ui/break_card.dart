import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../data/home_models.dart';
import 'live_clock.dart';

class BreakCard extends StatelessWidget {
  const BreakCard({
    super.key,
    required this.policy,
    required this.clock,
    required this.busy,
    required this.showAction,
    this.onAction,
    this.unavailableReason,
  });

  final BreakPolicy policy;
  final DateTime Function() clock;
  final bool busy;
  final bool showAction;
  final VoidCallback? onAction;
  final String? unavailableReason;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Break time', style: AppText.cardTitle),
          const SizedBox(height: AppSpace.x12),
          WorkedTicker(
            workedAtFetch: policy.usedSeconds,
            running: policy.isActive,
            receivedAt: policy.receivedAt,
            clock: clock,
            builder: (context, used) {
              final elapsed = used - policy.usedSeconds;
              return Wrap(
                spacing: AppSpace.x20,
                runSpacing: AppSpace.x8,
                children: [
                  _BreakMetric('Allowed', policy.allowedSeconds),
                  _BreakMetric('Used', used),
                  _BreakMetric(
                    'Remaining',
                    math.max(0, policy.remainingSeconds - elapsed),
                  ),
                ],
              );
            },
          ),
          if (unavailableReason != null) ...[
            const SizedBox(height: AppSpace.x10),
            Text(unavailableReason!, style: AppText.body),
          ],
          if (showAction) ...[
            const SizedBox(height: AppSpace.x12),
            AppButton(
              label: busy
                  ? 'Saving break…'
                  : policy.isActive
                  ? 'End break'
                  : 'Start break',
              tone: AppButtonTone.quiet,
              icon: policy.isActive
                  ? Icons.play_arrow_rounded
                  : Icons.pause_rounded,
              onPressed: busy ? null : onAction,
            ),
          ],
        ],
      ),
    );
  }
}

class _BreakMetric extends StatelessWidget {
  const _BreakMetric(this.label, this.seconds);

  final String label;
  final int seconds;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: AppText.meta),
      Text(formatHms(seconds), style: AppText.cardTitle),
    ],
  );
}
