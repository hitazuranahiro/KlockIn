import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';

/// A labeled field with a separate error line.
class AppInsetField extends StatefulWidget {
  const AppInsetField({
    super.key,
    required this.label,
    required this.controller,
    this.hintText,
    this.obscureText = false,
    this.keyboardType,
    this.onDark = false,
    this.errorText,
    this.autofillHints,
    this.enabled = true,
    this.suffixIcon,
    this.leadingIcon,
    this.focusNode,
    this.textInputAction,
    this.onSubmitted,
    this.fieldKey,
  });

  final String label;
  final TextEditingController controller;
  final String? hintText;
  final bool obscureText;
  final TextInputType? keyboardType;
  final bool onDark;
  final String? errorText;
  final Iterable<String>? autofillHints;
  final bool enabled;
  final Widget? suffixIcon;
  final IconData? leadingIcon;
  final FocusNode? focusNode;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;
  final Key? fieldKey;

  @override
  State<AppInsetField> createState() => _AppInsetFieldState();
}

class _AppInsetFieldState extends State<AppInsetField> {
  bool _focused = false;

  @override
  Widget build(BuildContext context) {
    final onDark = widget.onDark;
    final errorText = widget.errorText;
    final hasAccessories =
        widget.leadingIcon != null || widget.suffixIcon != null;
    const accessorySize = BoxConstraints.tightFor(width: 44, height: 44);
    final fill = onDark ? const Color(0x1AFFFFFF) : AppColors.surface;
    final border = _focused
        ? AppColors.brandStrong
        : onDark
        ? const Color(0x47FFFFFF)
        : AppColors.line;
    final valueColor = onDark ? AppColors.surface : AppColors.ink;
    final labelColor = _focused
        ? AppColors.brandStrong
        : onDark
        ? AppColors.onDark2
        : AppColors.ink3;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.label,
          style: AppText.cardTitle.copyWith(color: labelColor),
        ),
        const SizedBox(height: AppSpace.x6),
        Focus(
          onFocusChange: (focused) => setState(() => _focused = focused),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            padding: hasAccessories
                ? const EdgeInsets.fromLTRB(3, 4, 9, 4)
                : const EdgeInsets.symmetric(
                    horizontal: AppSpace.x16,
                    vertical: AppSpace.x12,
                  ),
            decoration: BoxDecoration(
              color: fill,
              borderRadius: BorderRadius.circular(AppRadii.field),
              border: Border.all(
                color: errorText == null ? border : AppColors.danger,
              ),
            ),
            child: Semantics(
              label: widget.label,
              child: TextField(
                key: widget.fieldKey,
                focusNode: widget.focusNode,
                enabled: widget.enabled,
                textInputAction: widget.textInputAction,
                onSubmitted: widget.onSubmitted,
                controller: widget.controller,
                obscureText: widget.obscureText,
                keyboardType: widget.keyboardType,
                textAlignVertical: TextAlignVertical.center,
                autofillHints: widget.autofillHints,
                style: AppText.cardTitle.copyWith(
                  color: valueColor,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                ),
                cursorColor: onDark ? AppColors.surface : AppColors.brandStrong,
                decoration: InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.zero,
                  border: InputBorder.none,
                  prefixIcon: widget.leadingIcon == null
                      ? null
                      : Icon(widget.leadingIcon, size: 20, color: labelColor),
                  prefixIconConstraints: accessorySize,
                  suffixIcon: widget.suffixIcon,
                  suffixIconConstraints: accessorySize,
                  hintText: widget.hintText,
                  hintStyle: AppText.cardTitle.copyWith(
                    color: AppColors.ink4,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ),
            ),
          ),
        ),
        if (errorText != null) ...[
          const SizedBox(height: AppSpace.x6),
          Text(
            errorText,
            style: AppText.meta.copyWith(color: AppColors.danger),
          ),
        ],
      ],
    );
  }
}
