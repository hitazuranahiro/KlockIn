"""Calculations shared by mobile attendance projection and the Home API."""

from datetime import UTC, datetime, timedelta


PAIRED = "paired"
FIRST_LAST = "first_last"
ATTENDANCE_MODES = [(PAIRED, "Paired Time In/Out"), (FIRST_LAST, "First In / Last Out")]


def elapsed_seconds(start, end):
    return max((end.astimezone(UTC) - start.astimezone(UTC)).total_seconds(), 0)


def _scheduled_break_ranges(start, end, policy):
    if not policy or not policy.break_start or not policy.break_end:
        return
    zone = start.tzinfo
    clock_end = end.astimezone(zone)
    day = start.date() - timedelta(days=1)
    while day <= clock_end.date():
        start_break = datetime.combine(day, policy.break_start, tzinfo=zone)
        end_day = day + timedelta(days=policy.break_end < policy.break_start)
        end_break = datetime.combine(end_day, policy.break_end, tzinfo=zone)
        yield start_break, end_break
        day += timedelta(days=1)


def _excluded_seconds(start, end, exclusions):
    """Count each second once when scheduled and employee breaks overlap."""
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    overlapped = sorted(
        (max(start, left.astimezone(UTC)), min(end, right.astimezone(UTC)))
        for left, right in exclusions
    )
    seconds = 0
    covered_until = start
    for left, right in overlapped:
        if right > max(left, covered_until):
            seconds += (right - max(left, covered_until)).total_seconds()
            covered_until = right
    return seconds


def duration_totals(ranges, policy=None, *, excluded_ranges=()):
    """Return paid time and unpaid break overlap on completed clock intervals."""
    completed = [(start, end) for start, end in ranges if end is not None]
    if not completed:
        return 0, 0
    if policy and policy.mode == FIRST_LAST:
        completed = [(min(start for start, _ in completed), max(end for _, end in completed))]
    excluded_ranges = tuple(excluded_ranges)
    unpaid_break = sum(
        _excluded_seconds(start, end, (*_scheduled_break_ranges(start, end, policy), *excluded_ranges))
        for start, end in completed
    )
    worked = sum(elapsed_seconds(start, end) for start, end in completed)
    return max(worked - unpaid_break, 0), unpaid_break
