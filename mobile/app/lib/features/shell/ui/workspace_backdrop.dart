import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';

/// Keeps the color drift in its own paint layer while menu controls stay still.
class WorkspaceBackdrop extends StatefulWidget {
  const WorkspaceBackdrop({super.key});

  @override
  State<WorkspaceBackdrop> createState() => _WorkspaceBackdropState();
}

class _WorkspaceBackdropState extends State<WorkspaceBackdrop>
    with SingleTickerProviderStateMixin {
  late final AnimationController _drift;
  late final AppLifecycleListener _lifecycle;
  bool _backgroundAllowed = false;

  @override
  void initState() {
    super.initState();
    _drift = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 18),
    );
    _lifecycle = AppLifecycleListener(onStateChange: (_) => _syncDrift());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _backgroundAllowed =
        !MediaQuery.disableAnimationsOf(context) &&
        !MediaQuery.highContrastOf(context) &&
        TickerMode.of(context) &&
        (ModalRoute.isCurrentOf(context) ?? true);
    _syncDrift();
  }

  void _syncDrift() {
    final state = WidgetsBinding.instance.lifecycleState;
    if (_backgroundAllowed &&
        (state == null || state == AppLifecycleState.resumed)) {
      if (!_drift.isAnimating) _drift.repeat();
    } else {
      _drift.stop();
    }
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _drift.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.highContrastOf(context)) {
      return const ColoredBox(color: AppColors.bg);
    }
    return RepaintBoundary(
      child: CustomPaint(
        painter: _WorkspaceGradient(
          MediaQuery.disableAnimationsOf(context) ? null : _drift,
        ),
      ),
    );
  }
}

class _WorkspaceGradient extends CustomPainter {
  _WorkspaceGradient(this.drift) : super(repaint: drift);

  final Animation<double>? drift;

  @override
  void paint(Canvas canvas, Size size) {
    final phase = (drift?.value ?? 0) * 2 * math.pi;
    final bounds = Offset.zero & size;
    final base = LinearGradient(
      begin: const Alignment(-0.85, -1),
      end: const Alignment(0.86, 1),
      colors: const [Color(0xFFBED4FE), Color(0xFFF5F8FF), Color(0xFFD3E3FD)],
      stops: [0, 0.49 + 0.05 * math.sin(phase), 1],
    );
    final light = RadialGradient(
      center: Alignment(
        0.43 + 0.47 * math.sin(phase),
        -0.28 - 0.40 * math.cos(phase),
      ),
      radius: 1.08,
      colors: const [Color(0xB58DB8FF), Color(0x008DB8FF)],
    );

    final paint = Paint()..shader = base.createShader(bounds);
    canvas.drawRect(bounds, paint);
    paint.shader = light.createShader(bounds);
    canvas.drawRect(bounds, paint);
  }

  @override
  bool shouldRepaint(_WorkspaceGradient oldDelegate) =>
      oldDelegate.drift != drift;
}
