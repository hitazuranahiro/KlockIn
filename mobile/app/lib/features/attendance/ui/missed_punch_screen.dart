import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_inset_field.dart';
import '../../../shared/widgets/app_primitives.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/toast.dart';
import '../../requests/data/requests_api.dart';
import '../data/attendance_api.dart';
import '../data/missed_punch_models.dart';

enum _PunchSelection {
  clockIn('Clock-in'),
  clockOut('Clock-out'),
  both('Both');

  const _PunchSelection(this.label);

  final String label;

  bool get includesIn => this != clockOut;
  bool get includesOut => this != clockIn;
}

class MissedPunchScreen extends ConsumerStatefulWidget {
  const MissedPunchScreen({super.key});

  @override
  ConsumerState<MissedPunchScreen> createState() => _MissedPunchScreenState();
}

class _MissedPunchScreenState extends ConsumerState<MissedPunchScreen> {
  final _clockIn = TextEditingController();
  final _clockOut = TextEditingController();
  final _reason = TextEditingController();
  DateTime _date = DateUtils.dateOnly(DateTime.now());
  _PunchSelection _selection = _PunchSelection.clockIn;
  bool _checkoutNextDay = false;
  bool _busy = false;
  String? _error;
  String? _inError;
  String? _outError;
  String? _reasonError;

  @override
  void dispose() {
    _clockIn.dispose();
    _clockOut.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(1900),
      lastDate: DateUtils.dateOnly(DateTime.now()),
    );
    if (!mounted || picked == null) return;
    setState(() {
      _date = picked;
      _error = null;
    });
  }

  Future<void> _submit() async {
    final timeIn = _selection.includesIn ? _clockIn.text.trim() : null;
    final timeOut = _selection.includesOut ? _clockOut.text.trim() : null;
    final reason = _reason.text.trim();
    setState(() {
      _error = null;
      _inError = timeIn != null && !MissedPunchDraft.isValidTime(timeIn)
          ? 'Enter a 24-hour time, such as 09:00.'
          : null;
      _outError = timeOut != null && !MissedPunchDraft.isValidTime(timeOut)
          ? 'Enter a 24-hour time, such as 18:00.'
          : null;
      if (_inError == null &&
          _outError == null &&
          timeIn != null &&
          timeOut != null &&
          !_checkoutNextDay &&
          timeOut.compareTo(timeIn) < 0) {
        _outError =
            'Turn on next-day clock-out if the shift ended after midnight.';
      }
      _reasonError = reason.isEmpty ? 'Enter a reason for this request.' : null;
    });
    if (_inError != null || _outError != null || _reasonError != null) return;

    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    try {
      await ref
          .read(attendanceApiProvider)
          .requestMissedPunch(
            MissedPunchDraft(
              attendanceDate: _date,
              reason: reason,
              timeIn: timeIn,
              timeOut: timeOut,
              checkoutNextDay: _checkoutNextDay,
            ),
          );
      if (!mounted) return;
      ref.invalidate(requestInboxProvider);
      ref
          .read(toastProvider.notifier)
          .show('Missed punch reported · pending approval');
      context.pop(true);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        if (failure is ApiValidation) {
          _inError = failure.forField('time_in');
          _outError =
              failure.forField('time_out') ??
              failure.forField('clock_out_date');
          _reasonError = failure.forField('reason');
        }
        _error = failure.message;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final includesIn = _selection.includesIn;
    final includesOut = _selection.includesOut;
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          AppTopBar(title: 'Report missed punch', onBack: () => context.pop()),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                AppSpace.screen,
                AppSpace.x18,
                AppSpace.screen,
                AppSpace.scrollBottom,
              ),
              children: [
                if (_error != null) ...[
                  Semantics(
                    liveRegion: true,
                    child: AppCard(
                      background: AppColors.dangerBg,
                      borderColor: AppColors.dangerBorder,
                      child: Text(
                        _error!,
                        style: AppText.body.copyWith(color: AppColors.danger),
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpace.x14),
                ],
                AppCard(
                  onTap: _busy ? null : _pickDate,
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const EyebrowLabel('Attendance date'),
                            const SizedBox(height: AppSpace.x6),
                            Text(
                              DateFormat('EEE, d MMM yyyy').format(_date),
                              style: AppText.cardTitle,
                            ),
                          ],
                        ),
                      ),
                      const Icon(
                        Icons.calendar_today_outlined,
                        size: 20,
                        color: AppColors.brandStrong,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpace.x18),
                const EyebrowLabel('Which punch did you miss?'),
                const SizedBox(height: AppSpace.x6),
                Wrap(
                  spacing: AppSpace.x8,
                  runSpacing: AppSpace.x6,
                  children: [
                    for (final option in _PunchSelection.values)
                      ChoiceChip(
                        label: Text(option.label),
                        selected: _selection == option,
                        onSelected: _busy
                            ? null
                            : (_) => setState(() {
                                _selection = option;
                                _error = null;
                                _inError = null;
                                _outError = null;
                              }),
                      ),
                  ],
                ),
                if (includesIn) ...[
                  const SizedBox(height: AppSpace.x14),
                  AppInsetField(
                    label: 'Clock-in time',
                    controller: _clockIn,
                    hintText: '09:00',
                    keyboardType: TextInputType.datetime,
                    enabled: !_busy,
                    errorText: _inError,
                  ),
                ],
                if (includesOut) ...[
                  const SizedBox(height: AppSpace.x14),
                  AppInsetField(
                    label: 'Clock-out time',
                    controller: _clockOut,
                    hintText: '18:00',
                    keyboardType: TextInputType.datetime,
                    enabled: !_busy,
                    errorText: _outError,
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Clock-out was the next day'),
                    controlAffinity: ListTileControlAffinity.leading,
                    value: _checkoutNextDay,
                    onChanged: _busy
                        ? null
                        : (selected) => setState(() {
                            _checkoutNextDay = selected ?? false;
                            _outError = null;
                          }),
                  ),
                ],
                const SizedBox(height: AppSpace.x18),
                const EyebrowLabel('Reason'),
                const SizedBox(height: AppSpace.x6),
                AppCard(
                  borderColor: _reasonError == null
                      ? AppColors.line
                      : AppColors.danger,
                  child: TextField(
                    controller: _reason,
                    enabled: !_busy,
                    maxLines: 3,
                    style: AppText.body,
                    decoration: const InputDecoration(
                      isDense: true,
                      border: InputBorder.none,
                      hintText: 'What happened?',
                    ),
                  ),
                ),
                if (_reasonError != null) ...[
                  const SizedBox(height: AppSpace.x6),
                  Text(
                    _reasonError!,
                    style: AppText.meta.copyWith(color: AppColors.danger),
                  ),
                ],
                const SizedBox(height: AppSpace.x12),
                const Text(
                  'Your attendance record will update after approval.',
                  style: AppText.meta,
                ),
              ],
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(AppSpace.screen),
              child: AppButton(
                label: _busy ? 'Submitting…' : 'Submit request',
                onPressed: _busy ? null : _submit,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
