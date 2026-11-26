import 'package:intl/intl.dart';

const missedPunchPath = '/attendance/missed-punch/';

enum MissedPunchStatus { pending, approved, rejected }

class MissedPunchDraft {
  const MissedPunchDraft({
    required this.attendanceDate,
    required this.reason,
    this.timeIn,
    this.timeOut,
    this.checkoutNextDay = false,
  });

  final DateTime attendanceDate;
  final String reason;
  final String? timeIn;
  final String? timeOut;
  final bool checkoutNextDay;

  static final _timePattern = RegExp(r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$');
  static String _wireDate(DateTime date) =>
      date.toIso8601String().split('T').first;

  static bool isValidTime(String value) => _timePattern.hasMatch(value);

  Map<String, dynamic> toJson() {
    final suppliedIn = timeIn?.trim();
    final suppliedOut = timeOut?.trim();
    return {
      'attendance_date': _wireDate(attendanceDate),
      if (suppliedIn != null && suppliedIn.isNotEmpty) 'time_in': suppliedIn,
      if (suppliedOut != null && suppliedOut.isNotEmpty) ...{
        'time_out': suppliedOut,
        if (checkoutNextDay)
          'clock_out_date': _wireDate(
            DateTime(
              attendanceDate.year,
              attendanceDate.month,
              attendanceDate.day + 1,
            ),
          ),
      },
      'reason': reason.trim(),
    };
  }
}

class MissedPunchRequest {
  const MissedPunchRequest({
    required this.id,
    required this.employeeId,
    required this.employeeName,
    required this.attendanceDate,
    required this.status,
    this.timeIn,
    this.timeOut,
    this.clockInDate,
    this.clockOutDate,
    this.reason,
    this.requestedAt,
  });

  final int id;
  final int employeeId;
  final String employeeName;
  final DateTime attendanceDate;
  final MissedPunchStatus status;
  final String? timeIn;
  final String? timeOut;
  final DateTime? clockInDate;
  final DateTime? clockOutDate;
  final String? reason;
  final DateTime? requestedAt;

  String get title => switch ((timeIn, timeOut)) {
    (final String _, final String _) => 'Missed clock-in and clock-out',
    (final String _, _) => 'Missed clock-in',
    _ => 'Missed clock-out',
  };

  String get timeSummary => [
    if (timeIn case final time?) 'Clock-in ${_displayTime(time, clockInDate)}',
    if (timeOut case final time?)
      'Clock-out ${_displayTime(time, clockOutDate)}',
  ].join(' · ');

  String _displayTime(String time, DateTime? date) {
    if (date == null ||
        MissedPunchDraft._wireDate(date) ==
            MissedPunchDraft._wireDate(attendanceDate)) {
      return time;
    }
    return '$time (${DateFormat('d MMM').format(date)})';
  }

  static MissedPunchRequest? fromJson(Object? value) {
    if (value is! Map<String, dynamic>) return null;
    final id = value['id'];
    final employeeId = value['employee_id'];
    final attendanceDate = _date(value['attendance_date']);
    final status = switch (value['status']) {
      'pending' => MissedPunchStatus.pending,
      'approved' => MissedPunchStatus.approved,
      'rejected' => MissedPunchStatus.rejected,
      _ => null,
    };
    final timeIn = _time(value['time_in']);
    final timeOut = _time(value['time_out']);
    if (id is! int ||
        employeeId is! int ||
        attendanceDate == null ||
        status == null ||
        (timeIn == null && timeOut == null)) {
      return null;
    }
    final name = [
      _text(value['employee_first_name']),
      _text(value['employee_last_name']),
    ].whereType<String>().join(' ');
    return MissedPunchRequest(
      id: id,
      employeeId: employeeId,
      employeeName: name.isEmpty ? 'Employee' : name,
      attendanceDate: attendanceDate,
      status: status,
      timeIn: timeIn,
      timeOut: timeOut,
      clockInDate: _date(value['clock_in_date']),
      clockOutDate: _date(value['clock_out_date']),
      reason: _text(value['reason']),
      requestedAt: _date(value['requested_at']),
    );
  }

  static DateTime? _date(Object? value) =>
      value is String ? DateTime.tryParse(value) : null;

  static String? _text(Object? value) =>
      value is String && value.trim().isNotEmpty ? value.trim() : null;

  static String? _time(Object? value) {
    if (value is! String || value.length < 5) return null;
    final formatted = value.substring(0, 5);
    return MissedPunchDraft.isValidTime(formatted) ? formatted : null;
  }
}
