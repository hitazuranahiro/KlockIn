import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/auth/session.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_primitives.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/error_state_card.dart';
import '../../approvals/data/approvals_controller.dart';
import '../../employee/data/employee_models.dart';
import '../../employee/ui/directory_screen.dart';
import '../../employee/ui/profile_sheet.dart';
import '../data/team_api.dart';
import '../data/team_models.dart';

/// A manager's view of their direct reports, today: who is in, who is off,
/// and whether this week's leave leaves the team thin.
class TeamScreen extends ConsumerWidget {
  const TeamScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final team = ref.watch(teamTodayProvider);
    final pending = ref.watch(approvalsProvider).value?.items.length ?? 0;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          const AppTopBar(title: 'People'),
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.screen,
              AppSpace.x8,
              AppSpace.screen,
              AppSpace.x12,
            ),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Wrap(
                spacing: AppSpace.x8,
                runSpacing: AppSpace.x6,
                children: [
                  OutlinedButton.icon(
                    onPressed: () => context.push('/team/directory'),
                    icon: const Icon(Icons.contacts_outlined, size: 18),
                    label: const Text('Directory'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => context.push('/team/approvals'),
                    icon: const Icon(Icons.fact_check_outlined, size: 18),
                    label: Text(
                      pending > 0 ? 'Approvals · $pending' : 'Approvals',
                    ),
                  ),
                ],
              ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              color: AppColors.brandStrong,
              onRefresh: () async {
                ref.invalidate(approvalsProvider);
                return ref.refresh(teamTodayProvider.future);
              },
              child: switch (team) {
                AsyncValue(:final value?) => _TeamBody(team: value),
                AsyncValue(:final error?) => ErrorStateCard(
                  failure: error is ApiFailure ? error : const ApiUnknown(),
                  onRetry: () => ref.invalidate(teamTodayProvider),
                ),
                _ => ListView(
                  padding: const EdgeInsets.all(AppSpace.screen),
                  children: const [
                    AppCard.skeleton(height: 92),
                    SizedBox(height: AppSpace.x16),
                    AppCard.skeleton(height: 220),
                  ],
                ),
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _TeamBody extends StatelessWidget {
  const _TeamBody({required this.team});

  final TeamToday team;

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(
        AppSpace.screen,
        AppSpace.x8,
        AppSpace.screen,
        AppSpace.scrollBottom,
      ),
      children: [
        const Text('My team', style: AppText.appBarTitle),
        const SizedBox(height: AppSpace.x4),
        Text(
          DateFormat('EEEE, d MMMM').format(DateTime.now()),
          style: AppText.meta,
        ),
        const SizedBox(height: AppSpace.x16),
        if (team.members.isEmpty)
          const Text(
            'Your team appears here after HR assigns you direct reports.',
            style: AppText.body,
          )
        else ...[
          Container(
            padding: const EdgeInsets.symmetric(vertical: AppSpace.x12),
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: AppColors.line),
                bottom: BorderSide(color: AppColors.line),
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final state in TeamState.values)
                  Expanded(
                    child: StatTile(
                      label: state.label,
                      value: '${team.count(state)}',
                      valueColor: switch (state) {
                        TeamState.checkedIn => AppColors.success,
                        TeamState.onLeave => AppColors.warningInk,
                        TeamState.notIn => AppColors.ink,
                      },
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.x20),
          const SectionHeader(title: 'Team roster'),
          const SizedBox(height: AppSpace.x8),
          for (final member in team.members) ...[
            const Divider(height: 1, color: AppColors.line),
            _MemberRow(member: member),
          ],
          if (team.week.isNotEmpty) ...[
            const SizedBox(height: AppSpace.x20),
            _WeekCoverage(team: team),
          ],
        ],
      ],
    );
  }
}

class _MemberRow extends StatelessWidget {
  const _MemberRow({required this.member});

  final TeamMember member;

  @override
  Widget build(BuildContext context) {
    final subtitle = switch (member.state) {
      TeamState.onLeave => member.leaveType ?? 'On leave',
      _ => member.jobPosition ?? member.state.label,
    };

    return InkWell(
      onTap: () => showProfileSheet(
        context,
        DirectoryEntry(
          id: member.id,
          firstName: member.name,
          lastName: '',
          jobPosition: member.jobPosition,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpace.x4,
          vertical: AppSpace.x12,
        ),
        child: Row(
          children: [
            AppAvatar.toned(name: member.name, size: 36),
            const SizedBox(width: AppSpace.x12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    member.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.cardTitle.copyWith(fontSize: 14),
                  ),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.meta,
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpace.x8),
            Flexible(
              child: Align(
                alignment: AlignmentDirectional.centerEnd,
                child: member.clockIn != null
                    ? Text(member.clockIn!, style: AppText.mono)
                    : StatusChip(
                        member.state.label,
                        tone: member.state == TeamState.onLeave
                            ? StatusTone.warning
                            : StatusTone.neutral,
                      ),
              ),
            ),
            const SizedBox(width: AppSpace.x4),
            const Icon(Icons.chevron_right, size: 17, color: AppColors.ink3),
          ],
        ),
      ),
    );
  }
}

/// Monday to Friday, shaded by how many of the team are off.
class _WeekCoverage extends StatelessWidget {
  const _WeekCoverage({required this.team});

  final TeamToday team;

  @override
  Widget build(BuildContext context) {
    final worst = team.worstDay;
    final weekOf = DateFormat('d MMM').format(team.week.first.date);

    return Container(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.line)),
      ),
      padding: const EdgeInsets.only(top: AppSpace.x16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'Leave coverage'),
          const SizedBox(height: AppSpace.x4),
          Text('Week of $weekOf', style: AppText.meta),
          const SizedBox(height: AppSpace.x12),
          Row(
            children: [
              for (var i = 0; i < team.week.length; i++) ...[
                if (i > 0) const SizedBox(width: AppSpace.x6),
                Expanded(child: _DayBlock(day: team.week[i])),
              ],
            ],
          ),
          const SizedBox(height: AppSpace.x10),
          Text(
            worst == null
                ? 'No day this week has more than one person off.'
                : '${DateFormat('EEEE').format(worst.date)}: '
                      '${worst.off.join(', ')} off. Coverage is thin that day.',
            style: AppText.meta.copyWith(
              color: worst == null ? AppColors.ink3 : AppColors.danger,
              fontWeight: worst == null ? null : FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _DayBlock extends StatelessWidget {
  const _DayBlock({required this.day});

  final ClashDay day;

  @override
  Widget build(BuildContext context) {
    final off = day.off.length;
    final (bg, ink) = off >= TeamToday.clashThreshold
        ? (AppColors.dangerBg, AppColors.danger)
        : off == 1
        ? (AppColors.warningBg, AppColors.warningInk)
        : (AppColors.bg, AppColors.ink4);

    return Semantics(
      label:
          '${DateFormat('EEEE').format(day.date)}: '
          '$off ${off == 1 ? 'person' : 'people'} off',
      excludeSemantics: true,
      child: Column(
        children: [
          Container(
            constraints: const BoxConstraints(minHeight: 36),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              off == 0 ? '–' : '$off',
              style: AppText.mono.copyWith(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: ink,
              ),
            ),
          ),
          const SizedBox(height: AppSpace.x4),
          Text(
            DateFormat('E').format(day.date),
            style: AppText.mono.copyWith(fontSize: 10, color: AppColors.ink4),
          ),
        ],
      ),
    );
  }
}

/// The Team tab's root: a manager's own team, or the directory for
/// everyone else. Decided by the role the server resolved at sign-in.
class TeamTab extends ConsumerWidget {
  const TeamTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isManager =
        ref.watch(sessionProvider)?.capabilities.isManager ?? false;
    return isManager ? const TeamScreen() : const DirectoryScreen();
  }
}
