import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/glass_surface.dart';
import '../../../shared/widgets/pressable.dart';
import '../data/home_models.dart';

class RoleBand extends StatelessWidget {
  const RoleBand({super.key, required this.count, this.subtitle, this.onTap});

  final int count;
  final String? subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return _WorkRow(
      icon: Icons.playlist_add_check_rounded,
      label: count == 1 ? '1 request to review' : '$count requests to review',
      detail: subtitle,
      onTap: onTap,
    );
  }
}

class QuickAction {
  const QuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
}

class QuickActions extends StatelessWidget {
  const QuickActions({super.key, required this.actions});

  final List<QuickAction> actions;

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      radius: AppRadii.hero,
      padding: const EdgeInsets.symmetric(horizontal: AppSpace.x16),
      child: Column(
        children: [
          for (final (index, action) in actions.indexed)
            _WorkRow(
              icon: action.icon,
              label: action.label,
              onTap: action.onTap,
              showDivider: index > 0,
            ),
        ],
      ),
    );
  }
}

class OnLeaveToday extends StatelessWidget {
  const OnLeaveToday({super.key, required this.colleagues, this.onTap});

  final List<ColleagueOnLeave> colleagues;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final count = colleagues.length;
    final names = colleagues
        .take(2)
        .map((colleague) => colleague.name)
        .join(', ');
    return _WorkRow(
      icon: Icons.event_busy_outlined,
      label: 'On leave today',
      detail: count > 2 ? '$names and ${count - 2} more' : names,
      onTap: onTap,
    );
  }
}

class AnnouncementCard extends StatelessWidget {
  const AnnouncementCard({
    super.key,
    required this.announcement,
    this.onTap,
    this.onSeeAll,
  });

  final AnnouncementSummary announcement;
  final VoidCallback? onTap;
  final VoidCallback? onSeeAll;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _WorkRow(
          icon: Icons.campaign_outlined,
          label: announcement.title,
          detail: 'Latest announcement',
          onTap: onTap,
        ),
        if (onSeeAll != null)
          TextButton(
            onPressed: onSeeAll,
            child: const Text('All announcements'),
          ),
      ],
    );
  }
}

class _WorkRow extends StatelessWidget {
  const _WorkRow({
    required this.icon,
    required this.label,
    this.detail,
    this.onTap,
    this.showDivider = true,
  });

  final IconData icon;
  final String label;
  final String? detail;
  final VoidCallback? onTap;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (showDivider) const Divider(height: 1, color: AppColors.line),
        Semantics(
          button: onTap != null,
          label: [label, if (detail != null) detail].join(', '),
          excludeSemantics: true,
          onTap: onTap,
          child: Pressable(
            onTap: onTap,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: kMinHitTarget),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 9),
                child: Row(
                  children: [
                    DecoratedBox(
                      decoration: BoxDecoration(
                        color: AppColors.brandTint,
                        borderRadius: BorderRadius.circular(AppRadii.iconTile),
                      ),
                      child: SizedBox.square(
                        dimension: 36,
                        child: Icon(
                          icon,
                          size: 19,
                          color: AppColors.brandStrong,
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpace.x12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(label, style: AppText.cardTitle),
                          if (detail != null && detail!.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(top: AppSpace.x4),
                              child: Text(detail!, style: AppText.meta),
                            ),
                        ],
                      ),
                    ),
                    if (onTap != null)
                      const Padding(
                        padding: EdgeInsets.only(left: AppSpace.x8),
                        child: Icon(
                          Icons.chevron_right_rounded,
                          size: 20,
                          color: AppColors.ink3,
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
