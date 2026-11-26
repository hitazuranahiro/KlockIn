import 'package:flutter/material.dart';
import 'package:printing/printing.dart';

import '../data/export_models.dart';

Widget buildPdfViewer(ExportPdfDocument document) => PdfPreview(
  build: (_) => document.bytes,
  useActions: false,
  allowPrinting: false,
  allowSharing: false,
  canChangePageFormat: false,
  canChangeOrientation: false,
  canDebug: false,
  dynamicLayout: false,
  onError: (_, _) =>
      const Center(child: Text('The PDF preview could not open.')),
);
