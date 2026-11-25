import 'dart:io';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../../../l10n/app_localizations.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/glass_surface.dart';

class PunchCameraScreen extends StatefulWidget {
  const PunchCameraScreen({super.key});

  @override
  State<PunchCameraScreen> createState() => _PunchCameraScreenState();
}

class _PunchCameraScreenState extends State<PunchCameraScreen>
    with WidgetsBindingObserver {
  CameraController? _camera;
  Uint8List? _photo;
  String? _error;
  bool _capturing = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _open();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _generation++;
      final camera = _camera;
      setState(() {
        _camera = null;
        _capturing = false;
        if (state == AppLifecycleState.paused) _photo = null;
      });
      camera?.dispose();
    } else if (state == AppLifecycleState.resumed &&
        _camera == null &&
        _photo == null) {
      _open();
    }
  }

  Future<void> _open() async {
    final generation = ++_generation;
    if (mounted) setState(() => _error = null);
    CameraController? camera;
    try {
      final cameras = await availableCameras();
      if (!mounted || generation != _generation) return;
      final front = cameras
          .where((camera) => camera.lensDirection == CameraLensDirection.front)
          .firstOrNull;
      if (front == null) {
        setState(() => _error = AppL10n.of(context).punchCameraUnavailable);
        return;
      }
      camera = CameraController(
        front,
        ResolutionPreset.medium,
        enableAudio: false,
      );
      await camera.initialize();
      if (!mounted || generation != _generation) {
        await camera.dispose();
        return;
      }
      setState(() => _camera = camera);
    } on CameraException catch (error) {
      await camera?.dispose();
      if (!mounted || generation != _generation) return;
      final l10n = AppL10n.of(context);
      setState(
        () => _error = error.code.startsWith('CameraAccess')
            ? l10n.punchCameraPermission
            : l10n.punchCameraOpenFailure,
      );
    }
  }

  Future<void> _capture() async {
    final camera = _camera;
    if (_capturing || camera == null) return;
    final generation = _generation;
    setState(() {
      _capturing = true;
      _error = null;
    });
    XFile? image;
    try {
      image = await camera.takePicture();
      final length = await image.length();
      if (!mounted || generation != _generation) return;
      if (length > 2 * 1024 * 1024) {
        setState(() => _error = AppL10n.of(context).punchPhotoTooLarge);
        return;
      }
      final bytes = await image.readAsBytes();
      if (!mounted || generation != _generation) return;
      // Keep the current capture in memory until the employee confirms it.
      // The temporary camera file is removed before they can retake it.
      setState(() => _photo = bytes);
    } catch (_) {
      if (mounted && generation == _generation) {
        setState(() => _error = AppL10n.of(context).punchPhotoFailure);
      }
    } finally {
      if (image != null) {
        try {
          await File(image.path).delete();
        } on FileSystemException {
          // The plugin writes to the platform's private temporary directory.
        }
      }
      if (mounted && generation == _generation) {
        setState(() => _capturing = false);
      }
    }
  }

  void _retake() {
    setState(() {
      _photo = null;
      _error = null;
    });
    if (_camera == null) _open();
  }

  @override
  void dispose() {
    _generation++;
    WidgetsBinding.instance.removeObserver(this);
    _camera?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final camera = _camera;
    final photo = _photo;
    final failure = _error;

    final title = photo == null
        ? l10n.punchCameraFrameTitle
        : l10n.punchCameraReviewTitle;
    final help = photo == null
        ? l10n.punchCameraFrameHelp
        : l10n.punchCameraReviewHelp;
    final actions = <Widget>[
      if (photo != null) ...[
        AppButton(
          label: l10n.punchCameraUse,
          icon: Icons.check_rounded,
          onPressed: _capturing
              ? null
              : () => Navigator.of(context).pop<Uint8List>(photo),
        ),
        const SizedBox(height: AppSpace.x8),
        AppButton(
          label: l10n.punchCameraRetake,
          icon: Icons.refresh_rounded,
          tone: AppButtonTone.quiet,
          compact: true,
          onPressed: _capturing ? null : _retake,
        ),
      ] else if (camera != null)
        AppButton(
          label: _capturing ? l10n.punchCameraCapturing : l10n.punchCameraTake,
          icon: Icons.camera_alt_outlined,
          onPressed: _capturing ? null : _capture,
        )
      else if (failure != null)
        AppButton(
          label: l10n.punchCameraRetry,
          icon: Icons.refresh_rounded,
          onPressed: _open,
        ),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.punchSelfieTitle),
        backgroundColor: AppColors.bg,
        surfaceTintColor: Colors.transparent,
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
        child: LayoutBuilder(
          builder: (context, constraints) {
            final previewHeight = (constraints.maxHeight * .68).clamp(
              170.0,
              480.0,
            );
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 20),
              children: [
                GlassSurface(
                  blur: 0,
                  padding: const EdgeInsets.all(AppSpace.x12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(5, 3, 5, 14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Semantics(
                              header: true,
                              child: Text(title, style: AppText.appBarTitle),
                            ),
                            const SizedBox(height: AppSpace.x6),
                            Text(
                              help,
                              style: AppText.body.copyWith(
                                color: AppColors.ink3,
                              ),
                            ),
                          ],
                        ),
                      ),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(AppRadii.card - 7),
                        child: SizedBox(
                          height: previewHeight,
                          child: ColoredBox(
                            color: AppColors.ink,
                            child: Center(
                              child: switch (photo) {
                                final Uint8List image => Image.memory(
                                  image,
                                  width: double.infinity,
                                  height: double.infinity,
                                  fit: BoxFit.contain,
                                  semanticLabel: l10n.punchCameraReviewTitle,
                                ),
                                _ when camera != null => CameraPreview(
                                  camera,
                                  child: const IgnorePointer(
                                    child: CustomPaint(painter: _FrameGuides()),
                                  ),
                                ),
                                _ when failure != null => const Icon(
                                  Icons.no_photography_outlined,
                                  size: 34,
                                  color: AppColors.surface,
                                ),
                                _ => CircularProgressIndicator(
                                  semanticsLabel: l10n.punchCameraStarting,
                                  color: AppColors.surface,
                                ),
                              },
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (failure != null) ...[
                  const SizedBox(height: AppSpace.x12),
                  Semantics(
                    liveRegion: true,
                    child: Container(
                      padding: const EdgeInsets.all(AppSpace.x12),
                      decoration: BoxDecoration(
                        color: AppColors.dangerBg,
                        borderRadius: BorderRadius.circular(AppRadii.field),
                      ),
                      child: Text(
                        failure,
                        style: AppText.body.copyWith(color: AppColors.danger),
                      ),
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      ),
      bottomNavigationBar: actions.isEmpty
          ? null
          : SafeArea(
              top: false,
              minimum: const EdgeInsets.fromLTRB(16, 6, 16, 10),
              child: GlassSurface(
                padding: const EdgeInsets.all(AppSpace.x10),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: actions,
                ),
              ),
            ),
    );
  }
}

class _FrameGuides extends CustomPainter {
  const _FrameGuides();

  @override
  void paint(Canvas canvas, Size size) {
    final frame = Rect.fromCenter(
      center: size.center(Offset.zero),
      width: size.width * .72,
      height: size.height * .69,
    );
    canvas.drawPath(
      Path()
        ..fillType = PathFillType.evenOdd
        ..addRect(Offset.zero & size)
        ..addRRect(RRect.fromRectAndRadius(frame, const Radius.circular(17))),
      Paint()..color = AppColors.ink.withValues(alpha: .26),
    );
    final paint = Paint()
      ..color = AppColors.surface
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = 2.75;
    const length = 22.0;

    for (final (corner, xDirection, yDirection) in [
      (frame.topLeft, 1, 1),
      (frame.topRight, -1, 1),
      (frame.bottomLeft, 1, -1),
      (frame.bottomRight, -1, -1),
    ]) {
      canvas.drawPath(
        Path()
          ..moveTo(corner.dx, corner.dy + yDirection * length)
          ..lineTo(corner.dx, corner.dy + yDirection * 11)
          ..quadraticBezierTo(
            corner.dx,
            corner.dy,
            corner.dx + xDirection * 11,
            corner.dy,
          )
          ..lineTo(corner.dx + xDirection * length, corner.dy),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_FrameGuides oldDelegate) => false;
}
