import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/api/host.dart';
import '../../../core/auth/session.dart';
import '../../../core/theme/tokens.dart';
import '../../../l10n/app_localizations.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_inset_field.dart';

class ServerSettingsScreen extends ConsumerStatefulWidget {
  const ServerSettingsScreen({
    super.key,
    required this.initialAddress,
    this.allowUse = true,
  });

  final String initialAddress;
  final bool allowUse;

  @override
  ConsumerState<ServerSettingsScreen> createState() => _ServerSettingsState();
}

class _ServerSettingsState extends ConsumerState<ServerSettingsScreen> {
  late final _serverAddress = TextEditingController(
    text: widget.initialAddress,
  );
  String? _result;
  bool _reachable = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _serverAddress.addListener(_clearResult);
  }

  void _clearResult() => setState(() {
    _reachable = false;
    _result = null;
  });

  @override
  void dispose() {
    _serverAddress.removeListener(_clearResult);
    _serverAddress.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    final l10n = AppL10n.of(context);
    final address = normaliseHost(_serverAddress.text);
    setState(() {
      _result = address.error;
      _reachable = false;
      _busy = address.isValid;
    });
    if (!address.isValid) return;
    try {
      await ref.read(authApiProvider).probe(address.host);
      if (mounted) {
        setState(() {
          _reachable = true;
          _result = l10n.signInServerReachable;
        });
      }
    } on ApiFailure catch (error) {
      if (mounted) setState(() => _result = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _use() {
    final address = normaliseHost(_serverAddress.text);
    if (!address.isValid) {
      setState(() {
        _reachable = false;
        _result = address.error;
      });
      return;
    }
    Navigator.of(context).pop(address.host);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.signInServerSettings),
        backgroundColor: AppColors.bg,
        surfaceTintColor: Colors.transparent,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 28),
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          children: [
            Text(
              l10n.serverAddressHelp,
              style: AppText.body.copyWith(color: AppColors.ink3, fontSize: 15),
            ),
            const SizedBox(height: 24),
            AppInsetField(
              label: l10n.serverAddressLabel,
              enabled: !_busy,
              controller: _serverAddress,
              hintText: l10n.signInServerHint,
              keyboardType: TextInputType.url,
              textInputAction: TextInputAction.done,
              onSubmitted: _busy ? null : (_) => _test(),
            ),
            if (normaliseHost(_serverAddress.text).isCleartext) ...[
              const SizedBox(height: 10),
              Text(
                l10n.signInCleartextWarning,
                style: AppText.body.copyWith(color: AppColors.warningInk),
              ),
            ],
            if (_result case final result?) ...[
              const SizedBox(height: 12),
              Semantics(
                liveRegion: true,
                child: Text(
                  result,
                  style: AppText.body.copyWith(
                    color: _reachable ? AppColors.success : AppColors.danger,
                  ),
                ),
              ),
            ],
            const SizedBox(height: 24),
            if (widget.allowUse) ...[
              AppButton(
                label: l10n.serverUseAddress,
                onPressed: _busy ? null : _use,
              ),
              const SizedBox(height: 8),
            ],
            AppButton(
              label: _busy ? l10n.signInTestBusy : l10n.signInTestConnection,
              onPressed: _busy ? null : _test,
              tone: widget.allowUse
                  ? AppButtonTone.quiet
                  : AppButtonTone.primary,
            ),
          ],
        ),
      ),
    );
  }
}
