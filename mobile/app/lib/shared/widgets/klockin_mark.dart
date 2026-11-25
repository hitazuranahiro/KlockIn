// Modified for KlockIN by Tomeku, 2026-11-25.
import 'package:flutter/widgets.dart';

import '../../core/theme/tokens.dart';

class KlockInMark extends StatelessWidget {
  const KlockInMark({super.key, this.size = 52});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      'Assets/klockin-mark.png',
      width: size,
      height: size,
      fit: BoxFit.contain,
      color: AppColors.brand,
      colorBlendMode: BlendMode.srcIn,
      excludeFromSemantics: true,
    );
  }
}

class KlockInLockup extends StatelessWidget {
  const KlockInLockup({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const KlockInMark(),
        const SizedBox(width: AppSpace.x12),
        Flexible(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('KlockIN', style: AppText.appBarTitle),
              const Text('by Tomeku', style: AppText.meta),
            ],
          ),
        ),
      ],
    );
  }
}

class KlockInMarkTile extends StatelessWidget {
  const KlockInMarkTile({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.line),
      ),
      alignment: Alignment.center,
      child: const KlockInMark(size: 28),
    );
  }
}
