import 'package:file_saver/file_saver.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:printing/printing.dart';

import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/toast.dart';
import '../data/export_models.dart';
import 'pdf_view_native.dart'
    if (dart.library.js_interop) 'pdf_view_web.dart'
    as viewer;

class ExportPdfTools {
  const ExportPdfTools();

  Widget preview(ExportPdfDocument document) => viewer.buildPdfViewer(document);

  Future<bool> download(ExportPdfDocument document) async {
    final name = document.filename.substring(0, document.filename.length - 4);
    final path = kIsWeb
        ? await FileSaver.instance.saveFile(
            name: name,
            bytes: document.bytes,
            fileExtension: 'pdf',
            mimeType: MimeType.pdf,
          )
        : await FileSaver.instance.saveAs(
            name: name,
            bytes: document.bytes,
            fileExtension: 'pdf',
            mimeType: MimeType.pdf,
          );
    return path != null && path.isNotEmpty;
  }

  Future<void> share(ExportPdfDocument document, Rect? bounds) async {
    await Printing.sharePdf(
      bytes: document.bytes,
      filename: document.filename,
      bounds: bounds,
    );
  }
}

final exportPdfToolsProvider = Provider<ExportPdfTools>(
  (_) => const ExportPdfTools(),
);

class ExportPreviewScreen extends ConsumerStatefulWidget {
  const ExportPreviewScreen({
    super.key,
    required this.target,
    required this.document,
  });

  final ExportTarget target;
  final ExportPdfDocument document;

  @override
  ConsumerState<ExportPreviewScreen> createState() =>
      _ExportPreviewScreenState();
}

class _ExportPreviewScreenState extends ConsumerState<ExportPreviewScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _export({required bool share, Rect? bounds}) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final tools = ref.read(exportPdfToolsProvider);
      if (share) {
        await tools.share(widget.document, bounds);
      } else {
        final saved = await tools.download(widget.document);
        if (saved && mounted) {
          ref
              .read(toastProvider.notifier)
              .show(kIsWeb ? 'Download started' : 'PDF saved');
        }
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _error = share
              ? 'Could not share the PDF.'
              : 'Could not save the PDF.';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Rect? _bounds(BuildContext context) {
    final box = context.findRenderObject();
    return box is RenderBox && box.hasSize
        ? box.localToGlobal(Offset.zero) & box.size
        : null;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          AppTopBar(
            title: '${widget.target.type.label} preview',
            onBack: ModalRoute.canPopOf(context) == true
                ? () => Navigator.maybePop(context)
                : null,
          ),
          Expanded(
            child: ref.watch(exportPdfToolsProvider).preview(widget.document),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(AppSpace.x12),
              child: Column(
                children: [
                  if (_error != null)
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        _error!,
                        style: AppText.meta.copyWith(color: AppColors.danger),
                      ),
                    ),
                  Wrap(
                    alignment: WrapAlignment.center,
                    spacing: AppSpace.x8,
                    runSpacing: AppSpace.x4,
                    children: [
                      FilledButton.icon(
                        onPressed: _busy ? null : () => _export(share: false),
                        icon: const Icon(Icons.download_outlined),
                        label: const Text('Download'),
                      ),
                      if (!kIsWeb)
                        Builder(
                          builder: (buttonContext) => OutlinedButton.icon(
                            onPressed: _busy
                                ? null
                                : () => _export(
                                    share: true,
                                    bounds: _bounds(buttonContext),
                                  ),
                            icon: const Icon(Icons.share_outlined),
                            label: const Text('Share'),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
