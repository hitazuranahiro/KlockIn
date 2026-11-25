from datetime import datetime, time, timedelta

from base.models import EmployeeShiftSchedule


WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
OVERNIGHT_CUTOFF = time(12)
DEFAULT_SCHEDULE = ("00:00", 0, 0)


def shift_schedules(shift_id):
    if shift_id is None:
        return [DEFAULT_SCHEDULE] * len(WEEKDAYS)
    schedules = {}
    for day, minimum, start, end in EmployeeShiftSchedule.objects.filter(
        shift_id_id=shift_id
    ).values_list("day__day", "minimum_working_hour", "start_time", "end_time"):
        if start is not None and end is not None:
            schedules[day] = (
                minimum,
                (start.hour * 60 + start.minute) * 60,
                (end.hour * 60 + end.minute) * 60,
            )
    return [schedules.get(day, DEFAULT_SCHEDULE) for day in WEEKDAYS]


def _rollover_time(day, schedules):
    previous_day = day - timedelta(days=1)
    _, start, end = schedules[previous_day.weekday()]
    return OVERNIGHT_CUTOFF if start > end else time.min


def workday_date(local_time, schedules):
    calendar_date = local_time.date()
    if local_time.time() < _rollover_time(calendar_date, schedules):
        return calendar_date - timedelta(days=1)
    return calendar_date


def workday_bounds(workday, schedules, zone):
    next_day = workday + timedelta(days=1)
    return (
        datetime.combine(workday, _rollover_time(workday, schedules), tzinfo=zone),
        datetime.combine(next_day, _rollover_time(next_day, schedules), tzinfo=zone),
    )
