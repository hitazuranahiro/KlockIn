// Modified for KlockIN by Tomeku, 2026-11-25.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/api/host.dart';
import '../../../core/auth/session.dart';
import '../../../core/theme/tokens.dart';
import '../../../l10n/app_localizations.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_inset_field.dart';
import '../../../shared/widgets/klockin_mark.dart';
import 'server_settings_screen.dart';

/// Server address provided by a workplace build, if one is configured.
const String kDefaultHost = String.fromEnvironment('KLOCKIN_SERVER_URL');
const _mastheadTop = Color(0xFF102D64);

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key, this.onSignedIn});

  final VoidCallback? onSignedIn;

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _host = TextEditingController(text: kDefaultHost);
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _identityFocus = FocusNode();
  final _passwordFocus = FocusNode();
  final _serverSection = GlobalKey();

  bool _useUsername = false;
  bool _busy = false;
  bool _testingServer = false;
  bool _showPassword = false;
  bool _editingServer = kDefaultHost.isEmpty;
  String? _connectionResult;
  String? _formError;
  String? _hostError;
  String? _usernameError;
  String? _passwordError;

  @override
  void initState() {
    super.initState();
    // The cleartext warning is derived from the host text, so the field has
    // to drive a rebuild -- a TextEditingController changing does not by
    // itself repaint anything outside the TextField.
    _host.addListener(_onHostChanged);
  }

  void _onHostChanged() => setState(() {
    _connectionResult = null;
    _hostError = null;
  });

  @override
  void dispose() {
    _host.removeListener(_onHostChanged);
    _host.dispose();
    _username.dispose();
    _password.dispose();
    _identityFocus.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  /// Warn about an unencrypted connection as it is typed, not after sign-in.
  bool get _isCleartext {
    final result = normaliseHost(_host.text);
    return result.isValid && result.isCleartext;
  }

  Future<void> _testConnection() async {
    if (_busy || _testingServer) return;
    final l10n = AppL10n.of(context);
    final address = normaliseHost(_host.text);
    setState(() {
      _hostError = address.error;
      _connectionResult = null;
      _testingServer = address.isValid;
    });
    if (!address.isValid) return;
    try {
      await ref.read(authApiProvider).probe(address.host);
      if (mounted) {
        setState(() => _connectionResult = l10n.signInServerReachable);
      }
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _hostError = failure.message);
    } finally {
      if (mounted) setState(() => _testingServer = false);
    }
  }

  Future<void> _submit() async {
    if (_busy || _testingServer) return;
    final l10n = AppL10n.of(context);
    final hostError = normaliseHost(_host.text).error;
    final identityError = _username.text.trim().isEmpty
        ? (_useUsername ? l10n.signInUsernameRequired : l10n.signInIdRequired)
        : null;
    final passwordError = _password.text.isEmpty
        ? l10n.signInPasswordRequired
        : null;
    final valid =
        hostError == null && identityError == null && passwordError == null;
    setState(() {
      _busy = valid;
      _formError = null;
      _hostError = hostError;
      _usernameError = identityError;
      _passwordError = passwordError;
    });
    if (!valid) {
      if (identityError != null) {
        _identityFocus.requestFocus();
      } else if (passwordError != null) {
        _passwordFocus.requestFocus();
      } else {
        FocusManager.instance.primaryFocus?.unfocus();
        _revealServerSection();
      }
      return;
    }

    FocusManager.instance.primaryFocus?.unfocus();
    try {
      await ref
          .read(sessionProvider.notifier)
          .signIn(
            rawHost: _host.text,
            username: _useUsername ? _username.text : null,
            employeeId: _useUsername ? null : _username.text.trim(),
            password: _password.text,
          );
      if (mounted) {
        TextInput.finishAutofillContext();
        widget.onSignedIn?.call();
      }
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        // Each of these needs different words. A locked account and a rate
        // limit are both 429; an unreachable host and a wrong password are
        // both "it didn't work" to a user who is not told otherwise.
        switch (failure) {
          case ApiIncompatibleServer():
          case ApiNetwork():
          case ApiTimeout():
          case ApiTls():
            _hostError = failure.message;
          case ApiUnauthenticated():
            _formError = l10n.signInBadCredentials;
          case ApiLockedOut():
          case ApiNoCompany():
          case ApiDeviceMismatch():
            _formError = failure.message;
          case ApiValidation(:final fieldErrors):
            _usernameError =
                fieldErrors[_useUsername ? 'username' : 'employee_id']?.first;
            _passwordError = fieldErrors['password']?.first;
            if (_usernameError == null && _passwordError == null) {
              _formError = failure.message;
            }
          default:
            _formError = failure.message;
        }
      });
      if (_hostError != null) _revealServerSection();
    } on Exception catch (error) {
      debugPrint('KlockIN sign-in could not finish: ${error.runtimeType}');
      if (mounted) setState(() => _formError = l10n.signInCouldNotFinish);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _revealServerSection() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final section = _serverSection.currentContext;
      if (section == null) return;
      Scrollable.ensureVisible(
        section,
        alignment: 0.18,
        duration: MediaQuery.disableAnimationsOf(section)
            ? Duration.zero
            : const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
      );
    });
  }

  bool get _showServer => _editingServer || _hostError != null || _isCleartext;

  Future<void> _openServerSettings() async {
    final address = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (_) => ServerSettingsScreen(initialAddress: _host.text),
      ),
    );
    if (address == null || !mounted) return;
    _host.text = address;
    setState(() => _editingServer = true);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final actionBusy = _busy || _testingServer;
    final needsSetup = _host.text.trim().isEmpty;

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: AnnotatedRegion<SystemUiOverlayStyle>(
        value: const SystemUiOverlayStyle(
          statusBarBrightness: Brightness.dark,
          statusBarIconBrightness: Brightness.light,
          systemNavigationBarColor: AppColors.surface,
          systemNavigationBarIconBrightness: Brightness.dark,
        ),
        child: SizedBox.expand(
          child: ColoredBox(
            color: MediaQuery.highContrastOf(context)
                ? AppColors.ink
                : _mastheadTop,
            child: SafeArea(
              left: false,
              right: false,
              bottom: false,
              child: ColoredBox(
                color: AppColors.surface,
                child: SingleChildScrollView(
                  keyboardDismissBehavior:
                      ScrollViewKeyboardDismissBehavior.onDrag,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _SignInMasthead(
                        title: l10n.signInHeadline,
                        description: l10n.signInSubcopy,
                      ),
                      SafeArea(
                        top: false,
                        child: Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 478),
                            child: Padding(
                              padding: const EdgeInsets.fromLTRB(
                                26,
                                26,
                                26,
                                24,
                              ),
                              child: AutofillGroup(
                                onDisposeAction: AutofillContextAction.cancel,
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    if (_formError case final message?) ...[
                                      _ErrorBanner(message: message),
                                      const SizedBox(height: AppSpace.x16),
                                    ],
                                    AppInsetField(
                                      fieldKey: const ValueKey(
                                        'sign-in-identity',
                                      ),
                                      label: _useUsername
                                          ? l10n.signInUsernameLabel
                                          : l10n.signInEmployeeIdLabel,
                                      controller: _username,
                                      focusNode: _identityFocus,
                                      leadingIcon: _useUsername
                                          ? Icons.person_outline_rounded
                                          : Icons.badge_outlined,
                                      errorText: _usernameError,
                                      enabled: !actionBusy,
                                      autofillHints: const [
                                        AutofillHints.username,
                                      ],
                                      textInputAction: TextInputAction.next,
                                      onSubmitted: (_) =>
                                          _passwordFocus.requestFocus(),
                                    ),
                                    const SizedBox(height: AppSpace.x16),
                                    AppInsetField(
                                      fieldKey: const ValueKey(
                                        'sign-in-password',
                                      ),
                                      label: l10n.signInPasswordLabel,
                                      controller: _password,
                                      focusNode: _passwordFocus,
                                      leadingIcon: Icons.lock_outline_rounded,
                                      obscureText: !_showPassword,
                                      errorText: _passwordError,
                                      enabled: !actionBusy,
                                      autofillHints: const [
                                        AutofillHints.password,
                                      ],
                                      textInputAction: TextInputAction.go,
                                      onSubmitted: actionBusy
                                          ? null
                                          : (_) => _submit(),
                                      suffixIcon: IconButton(
                                        tooltip: _showPassword
                                            ? l10n.signInHidePassword
                                            : l10n.signInShowPassword,
                                        onPressed: actionBusy
                                            ? null
                                            : () => setState(
                                                () => _showPassword =
                                                    !_showPassword,
                                              ),
                                        iconSize: 20,
                                        color: AppColors.ink3,
                                        icon: Icon(
                                          _showPassword
                                              ? Icons.visibility_off_outlined
                                              : Icons.visibility_outlined,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 22),
                                    AppButton(
                                      label: _busy
                                          ? l10n.signInBusy
                                          : l10n.signInAction,
                                      onPressed: actionBusy ? null : _submit,
                                    ),
                                    const SizedBox(height: 4),
                                    Center(
                                      child: TextButton(
                                        onPressed: actionBusy
                                            ? null
                                            : _switchIdentity,
                                        child: Text(
                                          _useUsername
                                              ? l10n.signInUseEmployeeId
                                              : l10n.signInUseUsername,
                                          textAlign: TextAlign.center,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: AppSpace.x10),
                                    const Divider(
                                      height: 1,
                                      color: AppColors.line,
                                    ),
                                    Column(
                                      key: _serverSection,
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        const SizedBox(height: AppSpace.x6),
                                        _ServerDisclosure(
                                          title: needsSetup
                                              ? l10n.signInWorkplaceSetup
                                              : l10n.signInConnection,
                                          expanded: _showServer,
                                          onTap: actionBusy || _isCleartext
                                              ? null
                                              : () => setState(() {
                                                  _editingServer = !_showServer;
                                                  _hostError = null;
                                                }),
                                        ),
                                        if (_showServer)
                                          _buildServerSettings(
                                            l10n,
                                            actionBusy,
                                          ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _switchIdentity() {
    setState(() {
      _useUsername = !_useUsername;
      _username.clear();
      _usernameError = null;
      _formError = null;
    });
  }

  Widget _buildServerSettings(AppL10n l10n, bool busy) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.bg,
        borderRadius: BorderRadius.circular(AppRadii.field),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AppInsetField(
              fieldKey: const ValueKey('sign-in-server'),
              label: l10n.signInServerLabel,
              controller: _host,
              keyboardType: TextInputType.url,
              hintText: l10n.signInServerHint,
              errorText: _hostError,
              enabled: !busy,
              textInputAction: TextInputAction.done,
              onSubmitted: busy ? null : (_) => _testConnection(),
            ),
            if (_isCleartext) ...[
              const SizedBox(height: AppSpace.x8),
              _CleartextWarning(message: l10n.signInCleartextWarning),
            ],
            const SizedBox(height: AppSpace.x4),
            Wrap(
              spacing: AppSpace.x8,
              children: [
                TextButton(
                  onPressed: busy ? null : _testConnection,
                  child: Text(
                    _testingServer
                        ? l10n.signInTestBusy
                        : l10n.signInTestConnection,
                  ),
                ),
                TextButton(
                  onPressed: busy ? null : _openServerSettings,
                  child: Text(l10n.signInServerSettings),
                ),
              ],
            ),
            if (_connectionResult case final result?)
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                child: Semantics(
                  liveRegion: true,
                  child: Text(
                    result,
                    style: AppText.body.copyWith(color: AppColors.success),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SignInMasthead extends StatelessWidget {
  const _SignInMasthead({required this.title, required this.description});

  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    final highContrast = MediaQuery.highContrastOf(context);
    return ClipRRect(
      borderRadius: const BorderRadius.vertical(bottom: Radius.circular(34)),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: highContrast ? AppColors.ink : null,
          gradient: highContrast
              ? null
              : const LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [_mastheadTop, Color(0xFF17418E), Color(0xFF2355B5)],
                  stops: [0, 0.58, 1],
                ),
        ),
        child: Stack(
          children: [
            if (!highContrast)
              const PositionedDirectional(
                top: -60,
                end: -124,
                width: 360,
                height: 360,
                child: IgnorePointer(
                  child: CustomPaint(painter: _ClockRings()),
                ),
              ),
            SafeArea(
              bottom: false,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 478),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(26, 24, 26, 29),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const _SignInBrand(),
                        const SizedBox(height: 32),
                        Semantics(
                          header: true,
                          child: Text(
                            title,
                            style: AppText.appBarTitle.copyWith(
                              fontSize: 36,
                              height: 1.06,
                              letterSpacing: -1.3,
                              color: AppColors.surface,
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          description,
                          style: AppText.body.copyWith(
                            fontSize: 15,
                            color: const Color(0xFFDCE8FF),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SignInBrand extends StatelessWidget {
  const _SignInBrand();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 46,
          height: 46,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: const Color(0x24FFFFFF),
            border: Border.all(color: const Color(0x45FFFFFF)),
            borderRadius: BorderRadius.circular(15),
          ),
          child: const ColorFiltered(
            colorFilter: ColorFilter.mode(AppColors.surface, BlendMode.srcIn),
            child: KlockInMark(size: 30),
          ),
        ),
        const SizedBox(width: AppSpace.x10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AppL10n.of(context).appTitle,
                style: AppText.cardTitle.copyWith(
                  color: AppColors.surface,
                  fontSize: 17,
                ),
              ),
              Text(
                'by Tomeku',
                style: AppText.meta.copyWith(color: const Color(0xFFDCE8FF)),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ClockRings extends CustomPainter {
  const _ClockRings();

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final ring = Paint()
      ..color = const Color(0x24A6C8FF)
      ..style = PaintingStyle.stroke;
    for (final radius in [68.0, 93.0, 119.0, 146.0, 173.0]) {
      canvas.drawCircle(center, radius, ring);
    }
  }

  @override
  bool shouldRepaint(_ClockRings oldDelegate) => false;
}

class _ServerDisclosure extends StatelessWidget {
  const _ServerDisclosure({
    required this.title,
    required this.expanded,
    required this.onTap,
  });

  final String title;
  final bool expanded;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      expanded: expanded,
      button: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.field),
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 54),
          child: Row(
            children: [
              const SizedBox(
                width: 36,
                child: Icon(
                  Icons.apartment_rounded,
                  size: 19,
                  color: AppColors.ink3,
                ),
              ),
              Expanded(
                child: Text(
                  title,
                  style: AppText.body.copyWith(color: AppColors.ink2),
                ),
              ),
              Icon(
                expanded
                    ? Icons.expand_less_rounded
                    : Icons.expand_more_rounded,
                size: 21,
                color: AppColors.ink3,
              ),
              const SizedBox(width: AppSpace.x6),
            ],
          ),
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpace.x12),
        decoration: BoxDecoration(
          color: AppColors.dangerBg,
          borderRadius: BorderRadius.circular(AppRadii.button),
          border: Border.all(color: AppColors.dangerBorder),
        ),
        child: Text(
          message,
          style: AppText.body.copyWith(color: AppColors.danger),
        ),
      ),
    );
  }
}

/// Unencrypted connections are permitted on a local network, but never
/// silently: the person signing in is told, every time.
class _CleartextWarning extends StatelessWidget {
  const _CleartextWarning({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.x10),
      decoration: BoxDecoration(
        color: AppColors.warningBg,
        borderRadius: BorderRadius.circular(AppRadii.button),
        border: Border.all(color: AppColors.warningBorder),
      ),
      child: Text(
        message,
        style: AppText.meta.copyWith(color: AppColors.warningInk),
      ),
    );
  }
}
