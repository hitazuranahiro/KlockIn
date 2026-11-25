// Modified for KlockIN by Tomeku, 2026-11-25.
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/theme/tokens.dart';
import '../../../l10n/app_localizations.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/glass_surface.dart';
import '../../../shared/widgets/hold_to_confirm_button.dart';
import '../../../shared/widgets/toast.dart';
import '../../home/data/home_models.dart';
import '../../home/ui/live_clock.dart';
import '../data/location_service.dart';
import '../data/punch_controller.dart';
import '../data/punch_queue.dart';
import 'punch_camera_screen.dart';
import 'punch_location_map.dart';

/// Captures attendance evidence and shows the receipt before returning to Today.
class PunchScreen extends ConsumerStatefulWidget {
  const PunchScreen({
    super.key,
    required this.isClockingIn,
    required this.geofence,
    this.today = TodayTotals.zero,
    this.clockInTime,
    this.captureSelfie,
  });

  final bool isClockingIn;
  final GeofenceState geofence;
  final TodayTotals today;
  final String? clockInTime;
  final Future<Uint8List?> Function(BuildContext)? captureSelfie;

  @override
  ConsumerState<PunchScreen> createState() => _PunchScreenState();
}

class _PunchScreenState extends ConsumerState<PunchScreen> {
  PunchPreparation? _preparation;
  bool _submitting = false;
  String? _error;

  String? _confirmedAt;
  final _addressLookup = PunchAddressLookup();
  PunchReceipt? _receipt;

  @override
  void initState() {
    super.initState();
    _prepare();
  }

  Future<void> _prepare() async {
    setState(() {
      _preparation = null;
      _error = null;
    });

    final preparation = await ref
        .read(punchControllerProvider)
        .prepare(isClockingIn: widget.isClockingIn, geofence: widget.geofence);
    if (mounted) setState(() => _preparation = preparation);
  }

  Future<void> _confirmThenSubmit() async {
    final preparation = _preparation;
    if (preparation == null ||
        !preparation.canSubmit ||
        _submitting ||
        _confirmedAt != null)
      return;

    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      final selfie =
          await (widget.captureSelfie?.call(context) ??
              Navigator.of(context).push<Uint8List>(
                MaterialPageRoute(builder: (_) => const PunchCameraScreen()),
              ));
      if (!mounted || selfie == null) return;
      final capturedAt = DateTime.now();
      final controller = ref.read(punchControllerProvider);
      final refreshed = await controller.prepare(
        isClockingIn: widget.isClockingIn,
        geofence: widget.geofence,
      );
      if (!mounted) return;
      setState(() => _preparation = refreshed);
      if (!refreshed.canSubmit) return;
      final receipt = await controller.submit(
        refreshed,
        selfie,
        punchedAt: capturedAt,
      );
      if (!mounted) return;
      final state = receipt.state;
      final l10n = AppL10n.of(context);
      if (state == PunchSyncState.rejected) {
        setState(() => _error = l10n.punchDeclined);
        return;
      }
      final at = DateFormat('HH:mm')
          .format((receipt.punchedAt ?? capturedAt).toLocal());
      ref.read(toastProvider.notifier).show(switch (state) {
        PunchSyncState.synced =>
          widget.isClockingIn ? l10n.punchClockedIn : l10n.punchClockedOut,
        PunchSyncState.review => l10n.punchUnderReview,
        _ =>
          refreshed.locationCheckPending
              ? l10n.punchSavedLocationPending
              : l10n.punchPending,
      });
      setState(() {
        _confirmedAt = at;
        _receipt = receipt;
      });
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } catch (_) {
      if (mounted)
        setState(() => _error = AppL10n.of(context).punchSaveFailure);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final preparation = _preparation;
    final verb = widget.isClockingIn ? l10n.punchIn : l10n.punchOut;
    final ready = (preparation?.canSubmit ?? false) && !_submitting;
    final confirmedAt = _confirmedAt;
    final blockedReason = preparation?.blockedReason;

    return Scaffold(
      appBar: AppBar(
        title: Text(verb),
        backgroundColor: AppColors.bg,
        surfaceTintColor: Colors.transparent,
        leading: BackButton(onPressed: () => context.pop(confirmedAt != null)),
      ),
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topRight,
            end: Alignment.bottomLeft,
            colors: [AppColors.brandTint, AppColors.bg, AppColors.surface],
            stops: [0, 0.58, 1],
          ),
        ),
        child: confirmedAt != null
            ? _PunchReceiptView(
                isClockingIn: widget.isClockingIn,
                at: confirmedAt,
                state: _receipt?.state,
                address: _receipt?.detectedAddress,
                siteName: preparation?.fence?.siteName,
                coordinates: preparation?.coordinates,
                addressLookup: _addressLookup,
              )
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 24),
                children: [
                  _LocationSection(
                    preparation: preparation,
                    addressLookup: _addressLookup,
                  ),
                  if (blockedReason != null) ...[
                    const SizedBox(height: 12),
                    _PunchNotice(text: blockedReason, isError: false),
                  ],
                  if (preparation != null && preparation.canSubmit == false)
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: TextButton.icon(
                        onPressed: _submitting ? null : _prepare,
                        icon: const Icon(Icons.refresh_rounded),
                        label: Text(l10n.punchLocationRetry),
                      ),
                    ),
                  if (!widget.isClockingIn) ...[
                    const SizedBox(height: 14),
                    GlassSurface(
                      blur: 0,
                      padding: const EdgeInsets.fromLTRB(16, 14, 16, 3),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _SectionTitle(l10n.punchShiftHeading),
                          _PunchFact(
                            label: l10n.punchStartTime,
                            value:
                                widget.clockInTime ?? l10n.punchTimeUnavailable,
                          ),
                          _PunchFact(
                            label: l10n.punchWorked,
                            value: formatHm(widget.today.workedSeconds),
                          ),
                          _PunchFact(
                            label: l10n.punchBreak,
                            value: formatShort(
                              TodayTotals.secondsOf(widget.today.breakTime) ??
                                  0,
                            ),
                            divider: false,
                          ),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),
                  _PunchInformation(
                    title: l10n.punchSelfieTitle,
                    detail: l10n.punchSelfieInstructions,
                    icon: Icons.camera_alt_outlined,
                  ),
                  if (_error case final error?) ...[
                    const SizedBox(height: 14),
                    _PunchNotice(text: error, isError: true),
                  ],
                ],
              ),
      ),
      bottomNavigationBar: _PunchActionArea(
        action: confirmedAt != null
            ? AppButton(
                label: l10n.punchDone,
                onPressed: () => context.pop(true),
              )
            : widget.isClockingIn
            ? AppButton(
                label: _submitting ? l10n.punchSaving : l10n.punchOpenCamera,
                icon: Icons.camera_alt_outlined,
                onPressed: ready ? _confirmThenSubmit : null,
              )
            : HoldToConfirmButton(
                label: _submitting ? l10n.punchSaving : l10n.punchHoldCamera,
                holdingLabel: l10n.punchHoldActive,
                enabled: ready,
                onConfirmed: _confirmThenSubmit,
              ),
        explanation: confirmedAt == null && !widget.isClockingIn && ready
            ? l10n.punchHoldHelp
            : null,
      ),
    );
  }
}

class _LocationSection extends StatelessWidget {
  const _LocationSection({
    required this.preparation,
    required this.addressLookup,
  });

  final PunchPreparation? preparation;
  final PunchAddressLookup addressLookup;

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final p = preparation;
    final coordinates = p?.coordinates;
    final headline = switch (p) {
      null => l10n.punchLocationChecking,
      PunchPreparation(:final fence?) => fence.description,
      PunchPreparation(locationCheckPending: true, coordinates: != null) =>
        l10n.punchLocationDeferred,
      PunchPreparation(blockedReason: null, coordinates: != null) =>
        l10n.punchLocationReady,
      _ => l10n.punchLocationNeeded,
    };
    final ready = p?.canSubmit == true;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          liveRegion: true,
          child: _PunchInformation(
            title: l10n.punchLocationHeading,
            detail: headline,
            icon: ready
                ? Icons.location_on_outlined
                : Icons.my_location_rounded,
          ),
        ),
        if (coordinates != null) ...[
          const SizedBox(height: 10),
          PunchLocationMap(
            latitude: coordinates.latitude,
            longitude: coordinates.longitude,
            addressLookup: addressLookup,
          ),
        ],
      ],
    );
  }
}

class _PunchReceiptView extends StatelessWidget {
  const _PunchReceiptView({
    required this.isClockingIn,
    required this.at,
    required this.state,
    required this.address,
    required this.siteName,
    required this.coordinates,
    required this.addressLookup,
  });

  final bool isClockingIn;
  final String at;
  final PunchSyncState? state;
  final String? address;
  final String? siteName;
  final Coordinates? coordinates;
  final PunchAddressLookup addressLookup;

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final (title, status, icon, accent, accentTint) = switch (state) {
      PunchSyncState.pending => (
        l10n.punchPending,
        l10n.punchAwaitingSync,
        Icons.cloud_upload_outlined,
        AppColors.warningInk,
        AppColors.warningBg,
      ),
      PunchSyncState.review => (
        l10n.punchReceived,
        l10n.punchUnderReview,
        Icons.pending_actions_outlined,
        AppColors.warningInk,
        AppColors.warningBg,
      ),
      _ => (
        isClockingIn ? l10n.punchClockedIn : l10n.punchClockedOut,
        l10n.punchSynced,
        Icons.check_rounded,
        AppColors.brandStrong,
        AppColors.brandTint,
      ),
    };

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 24),
      children: [
        GlassSurface(
          blur: 0,
          padding: const EdgeInsets.fromLTRB(19, 18, 19, 19),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Semantics(
                header: true,
                child: Text(
                  title,
                  style: AppText.appBarTitle.copyWith(fontSize: 26),
                ),
              ),
              const SizedBox(height: 7),
              Text(
                at,
                style: AppText.punchClock.copyWith(color: AppColors.ink),
              ),
              const SizedBox(height: 13),
              Semantics(
                liveRegion: true,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: accentTint,
                    borderRadius: BorderRadius.circular(AppRadii.field),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(10, 7, 12, 7),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(icon, color: accent, size: 17),
                        const SizedBox(width: 7),
                        Flexible(
                          child: Text(
                            status,
                            style: AppText.meta.copyWith(
                              color: accent,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        if (coordinates case final point?) ...[
          const SizedBox(height: 12),
          PunchLocationMap(
            latitude: point.latitude,
            longitude: point.longitude,
            address: address,
            addressLookup: addressLookup,
          ),
        ] else if (address?.trim() case final street?
            when street.isNotEmpty) ...[
          const SizedBox(height: 12),
          _PunchInformation(
            title: l10n.punchDetectedAddress,
            detail: street,
            icon: Icons.location_on_outlined,
          ),
        ],
        if (siteName?.trim() case final site?
            when site.isNotEmpty && site != address?.trim()) ...[
          const SizedBox(height: 12),
          _PunchInformation(
            title: l10n.punchLocationHeading,
            detail: site,
            icon: Icons.business_rounded,
          ),
        ],
      ],
    );
  }
}

class _PunchInformation extends StatelessWidget {
  const _PunchInformation({
    required this.title,
    required this.detail,
    required this.icon,
  });

  final String title;
  final String detail;
  final IconData icon;

  @override
  Widget build(BuildContext context) => GlassSurface(
    blur: 0,
    padding: const EdgeInsets.all(AppSpace.x14),
    child: Row(
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.brandTint,
            borderRadius: BorderRadius.circular(AppRadii.iconTile),
          ),
          child: Padding(
            padding: const EdgeInsets.all(11),
            child: Icon(icon, size: 21, color: AppColors.brandStrong),
          ),
        ),
        const SizedBox(width: AppSpace.x12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _SectionTitle(title),
              const SizedBox(height: 3),
              Text(detail, style: AppText.body.copyWith(color: AppColors.ink3)),
            ],
          ),
        ),
      ],
    ),
  );
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      header: true,
      child: Text(title, style: AppText.cardTitle.copyWith(fontSize: 17)),
    );
  }
}

class _PunchFact extends StatelessWidget {
  const _PunchFact({
    required this.label,
    required this.value,
    this.divider = true,
  });

  final String label;
  final String value;
  final bool divider;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: divider
          ? const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppColors.line)),
            )
          : null,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              label,
              style: AppText.body.copyWith(color: AppColors.ink3),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: AppText.mono.copyWith(color: AppColors.ink),
            ),
          ),
        ],
      ),
    );
  }
}

class _PunchActionArea extends StatelessWidget {
  const _PunchActionArea({required this.action, this.explanation});

  final Widget action;
  final String? explanation;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(16, 6, 16, 10),
      child: GlassSurface(
        padding: const EdgeInsets.all(AppSpace.x10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            action,
            if (explanation case final text?) ...[
              const SizedBox(height: 7),
              Text(text, style: AppText.meta, textAlign: TextAlign.center),
            ],
          ],
        ),
      ),
    );
  }
}

class _PunchNotice extends StatelessWidget {
  const _PunchNotice({required this.text, required this.isError});

  final String text;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isError ? AppColors.dangerBg : AppColors.warningBg,
          borderRadius: BorderRadius.circular(AppRadii.field),
        ),
        child: Text(
          text,
          style: AppText.body.copyWith(
            color: isError ? AppColors.danger : AppColors.warningInk,
          ),
        ),
      ),
    );
  }
}

class PunchArgs {
  const PunchArgs({
    required this.isClockingIn,
    required this.geofence,
    this.today = TodayTotals.zero,
    this.clockInTime,
  });

  final bool isClockingIn;
  final GeofenceState geofence;
  final TodayTotals today;
  final String? clockInTime;
}
