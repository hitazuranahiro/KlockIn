"""Calculations shared by mobile attendance projection and the Home API."""

from datetime import UTC, datetime, timedelta


PAIRED = "paired"
FIRST_LAST = "first_last"
ATTENDANCE_MODES = [(PAIRED, "Paired Time In/Out"), (FIRST_LAST, "First In / Last Out")]


def elapsed_seconds(start, end):
    return max((end.astimezone(UTC) - start.astimezone(UTC)).total_seconds(), 0)


def _scheduled_break_seconds(start, end, policy):
    if not policy or not policy.break_start or not policy.break_end or end <= start:
        return 0
    zone = start.tzinfo
    clock_end = end.astimezone(zone)
    day = start.date() - timedelta(days=1)
    seconds = 0
    while day <= clock_end.date():
        start_break = datetime.combine(day, policy.break_start, tzinfo=zone)
        end_day = day + timedelta(days=policy.break_end < policy.break_start)
        end_break = datetime.combine(end_day, policy.break_end, tzinfo=zone)
        seconds += elapsed_seconds(max(start, start_break), min(clock_end, end_break))
        day += timedelta(days=1)
    return seconds


def duration_totals(ranges, policy=None):
    """Return paid time and scheduled break overlap on completed clock intervals."""
    completed = [(start, end) for start, end in ranges if end is not None]
    if not completed:
        return 0, 0
    if policy and policy.mode == FIRST_LAST:
        completed = [(min(start for start, _ in completed), max(end for _, end in completed))]
    scheduled_break = sum(_scheduled_break_seconds(start, end, policy) for start, end in completed)
    worked = sum(elapsed_seconds(start, end) for start, end in completed)
    return max(worked - scheduled_break, 0), scheduled_break
