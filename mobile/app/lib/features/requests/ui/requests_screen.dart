import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_primitives.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/request_models.dart';
import '../data/requests_api.dart';

enum _Filter { all, pending, closed }

class RequestsScreen extends ConsumerStatefulWidget {
  const RequestsScreen({super.key});

  @override
  ConsumerState<RequestsScreen> createState() => _RequestsScreenState();
}

class _RequestsScreenState extends ConsumerState<RequestsScreen> {
  _Filter _filter = _Filter.all;

  @override
  Widget build(BuildContext context) {
    final inbox = ref.watch(requestInboxProvider);

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          const AppTopBar(title: 'Requests'),
          Expanded(
            child: RefreshIndicator(
              color: AppColors.brandStrong,
              onRefresh: () async => ref.refresh(requestInboxProvider.future),
              child: _body(
                inbox.value,
                error: inbox.value == null ? inbox.error : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(RequestInbox? inbox, {Object? error}) {
    final visible = switch (_filter) {
      _Filter.all => inbox?.requests,
      _Filter.pending => inbox?.open,
      _Filter.closed => inbox?.closed,
    };

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(
        AppSpace.screen,
        AppSpace.x12,
        AppSpace.screen,
        AppSpace.scrollBottom,
      ),
      children: [
        Wrap(
          spacing: AppSpace.x8,
          runSpacing: AppSpace.x8,
          children: [
            FilledButton.icon(
              onPressed: () => _openCreateSheet(context),
              icon: const Icon(Icons.add_rounded, size: 19),
              label: const Text('New request'),
            ),
            OutlinedButton.icon(
              onPressed: () => context.push('/requests/payslips'),
              icon: const Icon(Icons.receipt_long_outlined, size: 18),
              label: const Text('Payslips'),
            ),
          ],
        ),
        const SizedBox(height: AppSpace.x20),
        Wrap(
          spacing: AppSpace.x14,
          runSpacing: AppSpace.x4,
          children: [
            _RequestFilter(
              label: inbox == null ? 'All' : 'All ${inbox.requests.length}',
              selected: _filter == _Filter.all,
              select: () => setState(() => _filter = _Filter.all),
            ),
            _RequestFilter(
              label: inbox == null ? 'Pending' : 'Pending ${inbox.open.length}',
              selected: _filter == _Filter.pending,
              select: () => setState(() => _filter = _Filter.pending),
            ),
            _RequestFilter(
              label: 'Closed',
              selected: _filter == _Filter.closed,
              select: () => setState(() => _filter = _Filter.closed),
            ),
          ],
        ),
        const Divider(height: 1, color: AppColors.line),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpace.x14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Could not load requests', style: AppText.cardTitle),
                const SizedBox(height: AppSpace.x4),
                Text(
                  (error is ApiFailure ? error : const ApiUnknown()).message,
                  style: AppText.body,
                ),
                TextButton(
                  onPressed: () => ref.invalidate(requestInboxProvider),
                  child: const Text('Retry'),
                ),
              ],
            ),
          )
        else if (visible == null) ...[
          const SizedBox(height: AppSpace.x12),
          const AppCard.skeleton(height: 64),
          const SizedBox(height: AppSpace.x8),
          const AppCard.skeleton(height: 64),
        ] else if (visible.isEmpty)
          _EmptyRequests(filter: _filter)
        else
          for (final request in visible) ...[
            _RequestRow(request: request),
            const Divider(height: 1, color: AppColors.line),
          ],
      ],
    );
  }

  void _openCreateSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surface,
      showDragHandle: true,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppRadii.hero),
        ),
      ),
      builder: (sheetContext) => SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.x20,
            0,
            AppSpace.x20,
            AppSpace.x20,
          ),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'New request',
                  style: AppText.appBarTitle.copyWith(fontSize: 18),
                ),
                const SizedBox(height: AppSpace.x16),
                _CreateOption(
                  icon: Icons.schedule_outlined,
                  title: 'Shift / work type',
                  subtitle: 'Swap or change your work type',
                  onTap: () {
                    Navigator.of(sheetContext).pop();
                    context.push('/requests/shift-request');
                  },
                ),
                const SizedBox(height: AppSpace.x10),
                _CreateOption(
                  icon: Icons.receipt_long_outlined,
                  title: 'Reimbursement',
                  subtitle: 'Claim an expense',
                  onTap: () {
                    Navigator.of(sheetContext).pop();
                    context.push('/requests/reimburse');
                  },
                ),
                const SizedBox(height: AppSpace.x10),
                _CreateOption(
                  icon: Icons.devices_outlined,
                  title: 'Asset',
                  subtitle: 'Laptop, monitor…',
                  onTap: () {
                    Navigator.of(sheetContext).pop();
                    context.push('/requests/asset');
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RequestFilter extends StatelessWidget {
  const _RequestFilter({
    required this.label,
    required this.selected,
    required this.select,
  });

  final String label;
  final bool selected;
  final VoidCallback select;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      selected: selected,
      child: InkWell(
        onTap: select,
        child: Container(
          constraints: const BoxConstraints(minHeight: kMinHitTarget),
          padding: const EdgeInsets.symmetric(vertical: AppSpace.x12),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: selected ? AppColors.brandStrong : Colors.transparent,
                width: 2,
              ),
            ),
          ),
          child: Text(
            label,
            style: AppText.cardTitle.copyWith(
              color: selected ? AppColors.brandStrong : AppColors.ink3,
            ),
          ),
        ),
      ),
    );
  }
}

class _CreateOption extends StatelessWidget {
  const _CreateOption({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '$title, $subtitle',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: AppSpace.x12),
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: AppColors.line)),
          ),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: AppColors.brandTint,
                  borderRadius: BorderRadius.circular(AppRadii.field),
                ),
                child: Icon(icon, size: 20, color: AppColors.brandStrong),
              ),
              const SizedBox(width: AppSpace.x12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: AppText.cardTitle.copyWith(fontSize: 14),
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle, style: AppText.meta),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.ink4),
            ],
          ),
        ),
      ),
    );
  }
}

class _RequestRow extends StatelessWidget {
  const _RequestRow({required this.request});

  final WorkRequest request;

  @override
  Widget build(BuildContext context) {
    final meta = [
      if (request.date != null) DateFormat('d MMM').format(request.date!),
      if (request.detail != null) request.detail!,
    ].join(' · ');

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpace.x14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            _requestIcon(request.kind),
            size: 20,
            color: AppColors.brandStrong,
          ),
          const SizedBox(width: AppSpace.x12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(request.title, style: AppText.cardTitle),
                const SizedBox(height: AppSpace.x4),
                Text(
                  [request.kind.label, if (meta.isNotEmpty) meta].join(' · '),
                  style: AppText.meta,
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpace.x8),
          Flexible(
            child: Align(
              alignment: AlignmentDirectional.topEnd,
              child: StatusChip(
                request.state.label,
                tone: _tone(request.state),
              ),
            ),
          ),
        ],
      ),
    );
  }

  IconData _requestIcon(RequestKind kind) => switch (kind) {
    RequestKind.shift => Icons.schedule_outlined,
    RequestKind.workType => Icons.work_outline,
    RequestKind.asset => Icons.devices_outlined,
    RequestKind.reimbursement => Icons.receipt_long_outlined,
    RequestKind.attendance => Icons.edit_calendar_outlined,
  };

  StatusTone _tone(RequestState state) => switch (state) {
    RequestState.approved => StatusTone.success,
    RequestState.rejected => StatusTone.danger,
    RequestState.cancelled => StatusTone.neutral,
    RequestState.pending => StatusTone.warning,
  };
}

class _EmptyRequests extends StatelessWidget {
  const _EmptyRequests({required this.filter});

  final _Filter filter;

  @override
  Widget build(BuildContext context) {
    final message = switch (filter) {
      _Filter.pending => 'No requests await a decision.',
      _Filter.closed => 'No closed requests yet.',
      _Filter.all => 'Your requests will appear here.',
    };

    return Padding(
      padding: const EdgeInsets.only(top: AppSpace.x20),
      child: Text(message, style: AppText.body),
    );
  }
}
