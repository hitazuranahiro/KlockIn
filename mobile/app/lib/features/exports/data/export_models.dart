import 'dart:typed_data';

import 'package:intl/intl.dart';

enum ExportDocumentType {
  payslip('Payslip', 'payslip'),
  dtr('DTR', 'dtr');

  const ExportDocumentType(this.label, this.preferenceKey);

  final String label;
  final String preferenceKey;

  Map<String, String> get layouts => switch (this) {
    payslip => {
      'detailed': 'Detailed',
      'landscape': 'Landscape',
      'compact': 'Compact',
    },
    dtr => {'am-pm': 'AM / PM', 'first-last': 'First in / Last out'},
  };

  String get layoutKey => this == payslip ? 'template' : 'layout';
}

class ExportTarget {
  const ExportTarget.payslip({required int id, required this.period})
    : type = ExportDocumentType.payslip,
      _payslipId = id;

  const ExportTarget.dtr({required this.period})
    : type = ExportDocumentType.dtr,
      _payslipId = null;

  final ExportDocumentType type;
  final DateTime period;
  final int? _payslipId;

  String get formattedPeriod => DateFormat('MMMM yyyy').format(period);

  String get month =>
      '${period.year.toString().padLeft(4, '0')}-'
      '${period.month.toString().padLeft(2, '0')}';

  String get path => switch (type) {
    ExportDocumentType.payslip => '/payroll/payslip-download/$_payslipId',
    ExportDocumentType.dtr => '/mobile/dtr/',
  };

  String get fallbackFilename => switch (type) {
    ExportDocumentType.payslip => 'payslip-$month.pdf',
    ExportDocumentType.dtr => 'dtr-$month.pdf',
  };
}

class ExportSettings {
  const ExportSettings({
    required this.layout,
    this.orientation = 'portrait',
    this.showCompany = true,
    this.showNotes = true,
    this.note = '',
    this.showUndertime = true,
  });

  static const orientations = {
    'portrait': 'Portrait',
    'landscape': 'Landscape',
  };
  static const maxNoteLength = 160;

  final String layout;
  final String orientation;
  final bool showCompany;
  final bool showNotes;
  final String note;
  final bool showUndertime;

  factory ExportSettings.fromJson(
    ExportDocumentType type,
    Map<String, dynamic> data,
  ) {
    final layout = data[type.layoutKey];
    final orientation = data['orientation'];
    return ExportSettings(
      layout: layout is String && type.layouts.containsKey(layout)
          ? layout
          : type.layouts.keys.first,
      orientation:
          orientation is String && orientations.containsKey(orientation)
          ? orientation
          : 'portrait',
      showCompany: data['show_company'] != false,
      showNotes: data['show_notes'] != false,
      note: data['note'] is String ? data['note'] as String : '',
      showUndertime: data['show_undertime'] != false,
    );
  }

  ExportSettings copyWith({
    String? layout,
    String? orientation,
    bool? showCompany,
    bool? showNotes,
    String? note,
    bool? showUndertime,
  }) => ExportSettings(
    layout: layout ?? this.layout,
    orientation: orientation ?? this.orientation,
    showCompany: showCompany ?? this.showCompany,
    showNotes: showNotes ?? this.showNotes,
    note: note ?? this.note,
    showUndertime: showUndertime ?? this.showUndertime,
  );

  Map<String, dynamic> toPreferences(ExportDocumentType type) => {
    type.layoutKey: layout,
    'show_company': showCompany,
    'show_notes': showNotes,
    'note': note,
    if (type == ExportDocumentType.dtr) ...{
      'orientation': orientation,
      'show_undertime': showUndertime,
    },
  };

  Map<String, dynamic> toPdfQuery(ExportTarget target) => {
    target.type.layoutKey: layout,
    'show_company': showCompany ? '1' : '0',
    'show_notes': showNotes ? '1' : '0',
    'preview': '1',
    if (target.type == ExportDocumentType.payslip)
      'format': 'pdf'
    else ...{
      'month': target.month,
      'orientation': orientation,
      'show_undertime': showUndertime ? '1' : '0',
    },
  };
}

class ExportPdfDocument {
  const ExportPdfDocument({required this.bytes, required this.filename});

  final Uint8List bytes;
  final String filename;
}
