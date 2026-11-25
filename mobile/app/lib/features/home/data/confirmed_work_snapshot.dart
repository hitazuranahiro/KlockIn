/// A server-confirmed total and the interval in which its workday is current.
class ConfirmedWorkSnapshot {
  const ConfirmedWorkSnapshot._({
    required this.worked,
    required this.workedSeconds,
    required this.workday,
    required this.timeZone,
    required this.confirmedAt,
    required this.confirmedAtSiteTime,
    required this.workdayStartsAt,
    required this.workdayEndsAt,
    required String confirmedAtWire,
  }) : _confirmedAtWire = confirmedAtWire;

  final String worked;
  final int workedSeconds;
  final String workday;
  final String timeZone;
  final DateTime confirmedAt;

  /// Wall-clock fields from the original server timestamp, for display.
  final DateTime confirmedAtSiteTime;
  final DateTime workdayStartsAt;
  final DateTime workdayEndsAt;
  final String _confirmedAtWire;

  static final _zoneSuffix = RegExp(r'(Z|[+-]\d\d:\d\d)$');

  bool isCurrentAt(DateTime now) =>
      !now.isBefore(confirmedAt) && now.isBefore(workdayEndsAt);

  static ConfirmedWorkSnapshot? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final worked = json['worked'];
    final workday = json['workday'];
    final timeZone = json['time_zone'];
    final confirmedAtWire = json['confirmed_at'];
    if (worked is! String ||
        workday is! String ||
        timeZone is! String ||
        timeZone.trim().isEmpty ||
        confirmedAtWire is! String) {
      return null;
    }

    final duration = RegExp(
      r'^(\d{1,5}):([0-5]\d):([0-5]\d)$',
    ).firstMatch(worked);
    final date = DateTime.tryParse('${workday}T00:00:00Z');
    final confirmedAt = _awareDateTime(confirmedAtWire);
    final confirmedAtSiteTime = DateTime.tryParse(
      confirmedAtWire.replaceFirst(_zoneSuffix, 'Z'),
    );
    final startsAt = _awareDateTime(json['workday_starts_at']);
    final endsAt = _awareDateTime(json['workday_ends_at']);
    if (duration == null ||
        date == null ||
        date.toIso8601String().split('T').first != workday ||
        confirmedAt == null ||
        confirmedAtSiteTime == null ||
        startsAt == null ||
        endsAt == null ||
        confirmedAt.isBefore(startsAt) ||
        !confirmedAt.isBefore(endsAt)) {
      return null;
    }

    return ConfirmedWorkSnapshot._(
      worked: worked,
      workedSeconds:
          int.parse(duration[1]!) * 3600 +
          int.parse(duration[2]!) * 60 +
          int.parse(duration[3]!),
      workday: workday,
      timeZone: timeZone,
      confirmedAt: confirmedAt,
      confirmedAtSiteTime: confirmedAtSiteTime,
      workdayStartsAt: startsAt,
      workdayEndsAt: endsAt,
      confirmedAtWire: confirmedAtWire,
    );
  }

  static DateTime? _awareDateTime(Object? value) =>
      value is String && _zoneSuffix.hasMatch(value)
      ? DateTime.tryParse(value)?.toUtc()
      : null;

  Map<String, dynamic> toJson() => {
    'worked': worked,
    'workday': workday,
    'time_zone': timeZone,
    'confirmed_at': _confirmedAtWire,
    'workday_starts_at': workdayStartsAt.toIso8601String(),
    'workday_ends_at': workdayEndsAt.toIso8601String(),
  };
}
