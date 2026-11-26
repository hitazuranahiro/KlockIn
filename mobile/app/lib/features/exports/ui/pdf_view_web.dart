import 'dart:js_interop';

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

import '../data/export_models.dart';

Widget buildPdfViewer(ExportPdfDocument document) => _BrowserPdf(document);

class _BrowserPdf extends StatefulWidget {
  const _BrowserPdf(this.document);

  final ExportPdfDocument document;

  @override
  State<_BrowserPdf> createState() => _BrowserPdfState();
}

class _BrowserPdfState extends State<_BrowserPdf> {
  late final String _url;

  @override
  void initState() {
    super.initState();
    final blob = web.Blob(
      <JSAny>[widget.document.bytes.toJS].toJS,
      web.BlobPropertyBag(type: 'application/pdf'),
    );
    _url = web.URL.createObjectURL(blob);
  }

  @override
  void dispose() {
    web.URL.revokeObjectURL(_url);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => HtmlElementView.fromTagName(
    tagName: 'iframe',
    onElementCreated: (element) {
      final frame = element as web.HTMLIFrameElement;
      frame
        ..src = _url
        ..title = 'PDF preview';
      frame.style
        ..width = '100%'
        ..height = '100%'
        ..border = '0';
    },
  );
}
