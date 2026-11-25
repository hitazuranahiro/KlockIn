from io import BytesIO

from django.http import FileResponse
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from attendance.methods.utils import strtime_seconds

from .projection import CORRECTION_PREFIX


MARGIN = 26
GUTTER = 22
TABLE_TOP = 704
ROW_HEIGHT = 13


def _clock_text(clock, clock_date, workday, *, show_period):
    if clock is None:
        return ""
    text = clock.strftime("%I:%M %p" if show_period else "%I:%M").lstrip("0")
    if clock_date is not None and clock_date > workday:
        text += f" +{(clock_date - workday).days}"
    return text


def _punch_date(clock_date, recorded_at):
    if clock_date is not None or recorded_at is None:
        return clock_date
    return timezone.localtime(recorded_at, timezone.get_default_timezone()).date()


def _daily_clocks(row, activities, use_first_last):
    official_pair = (
        row.attendance_clock_in,
        row.attendance_clock_in_date,
        row.attendance_clock_out,
        row.attendance_clock_out_date,
    )
    if use_first_last:
        return [
            _clock_text(clock, clock_date, row.attendance_date, show_period=True)
            for clock, clock_date in (official_pair[:2], official_pair[2:])
        ]

    if not activities or row.history.filter(
        history_change_reason__startswith=CORRECTION_PREFIX
    ).exists():
        pairs = [official_pair]
    else:
        pairs = [
            (
                entry.clock_in,
                _punch_date(entry.clock_in_date, entry.in_datetime),
                entry.clock_out,
                _punch_date(entry.clock_out_date, entry.out_datetime),
            )
            for entry in activities
        ]

    clocks = ["", "", "", ""]
    for clock_in, in_date, clock_out, out_date in pairs:
        if clock_in is not None:
            column = 0 if clock_in.hour < 12 else 2
            if not clocks[column]:
                clocks[column] = _clock_text(
                    clock_in, in_date, row.attendance_date, show_period=False
                )
        if clock_out is not None:
            column = 1 if clock_out.hour < 12 else 3
            clocks[column] = _clock_text(
                clock_out, out_date, row.attendance_date, show_period=False
            )
    return clocks


def _monthly_cells(last_day, rows, intervals, use_first_last):
    days = []
    total = 0
    for day in range(1, 32):
        row = rows.get(day) if day <= last_day else None
        clocks = [""] * (2 if use_first_last else 4)
        undertime = ("", "")
        if row is not None:
            clocks = _daily_clocks(row, intervals.get(day, ()), use_first_last)
            if row.attendance_clock_out is not None:
                worked = row.at_work_second
                if worked is None:
                    worked = strtime_seconds(row.attendance_worked_hour or "00:00")
                minimum = strtime_seconds(row.minimum_hour or "00:00")
                minutes = max(0, minimum - worked) // 60
                undertime = divmod(minutes, 60)
                total += minutes
        days.append((day, *clocks, *undertime))
    return days, divmod(total, 60)


def _draw_header(pdf, employee, month, width):
    pdf.setFont("Helvetica", 8)
    pdf.drawString(0, 816, "CS Form No. 48 style")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(width / 2, 796, "DAILY TIME RECORD")

    name_columns = (
        ("Last Name", employee.employee_last_name),
        ("First Name", employee.employee_first_name),
        ("Middle Name", ""),
    )
    name_width = width / len(name_columns)
    pdf.line(0, 766, width, 766)
    for index, (label, value) in enumerate(name_columns):
        center = (index + 0.5) * name_width
        name = " ".join((value or "").split())
        if name:
            font = "Helvetica-Bold"
            natural_width = stringWidth(name, font, 1)
            size = min(9, (name_width - 8) / natural_width) if natural_width else 9
            pdf.setFont(font, size)
            pdf.drawCentredString(center, 771, name)
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(center, 756, label)

    pdf.setFont("Helvetica", 8)
    pdf.drawString(0, 741, "For the month of")
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString((68 + width) / 2, 741, month.strftime("%B %Y"))
    pdf.line(68, 739, width, 739)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(0, 728, "Official hours for arrival and departure")
    pdf.drawString(0, 716, "Regular days")
    pdf.line(53, 714, width / 2 + 8, 714)
    pdf.drawString(width / 2 + 16, 716, "Saturdays")
    pdf.line(width / 2 + 56, 714, width, 714)


def _draw_grid(pdf, days, total, width, use_first_last):
    clock_count = 2 if use_first_last else 4
    day_width = 23
    hours_width = 28
    minutes_width = 33
    clock_width = (width - day_width - hours_width - minutes_width) / clock_count
    times_end = width - hours_width - minutes_width
    columns = [
        0,
        *(day_width + index * clock_width for index in range(clock_count + 1)),
        width - minutes_width,
        width,
    ]
    split_header = TABLE_TOP - ROW_HEIGHT
    days_top = split_header - ROW_HEIGHT
    total_top = days_top - len(days) * ROW_HEIGHT
    bottom = total_top - ROW_HEIGHT

    for index, x in enumerate(columns):
        if index in (0, len(columns) - 3, len(columns) - 2, len(columns) - 1):
            y = bottom
        else:
            y = total_top
        splits_group = index == len(columns) - 2 or (not use_first_last and index in (2, 4))
        pdf.line(x, split_header if splits_group else TABLE_TOP, x, y)
    pdf.line(0, TABLE_TOP, width, TABLE_TOP)
    pdf.line(times_end if use_first_last else day_width, split_header, width, split_header)
    for row in range(len(days) + 2):
        y = days_top - row * ROW_HEIGHT
        pdf.line(0, y, width, y)

    def center(index):
        return (columns[index] + columns[index + 1]) / 2

    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(center(0), TABLE_TOP - 16, "Day")
    pdf.drawCentredString((times_end + width) / 2, TABLE_TOP - 9, "UNDERTIME")
    if use_first_last:
        pdf.drawCentredString(center(1), TABLE_TOP - 16, "First In")
        pdf.drawCentredString(center(2), TABLE_TOP - 16, "Last Out")
    else:
        pdf.drawCentredString(columns[2], TABLE_TOP - 9, "A.M.")
        pdf.drawCentredString(columns[4], TABLE_TOP - 9, "P.M.")
        for index, label in enumerate(("Arrival", "Departure", "Arrival", "Departure"), 1):
            pdf.drawCentredString(center(index), split_header - 9, label)
    pdf.drawCentredString(center(len(columns) - 3), split_header - 9, "Hours")
    pdf.drawCentredString(center(len(columns) - 2), split_header - 9, "Minutes")

    pdf.setFont("Helvetica", 8)
    for index, values in enumerate(days):
        y = days_top - index * ROW_HEIGHT - 9
        for column, value in enumerate(values):
            pdf.drawCentredString(center(column), y, str(value))

    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(times_end / 2, total_top - 9, "TOTAL")
    pdf.drawCentredString(center(len(columns) - 3), total_top - 9, str(total[0]))
    pdf.drawCentredString(center(len(columns) - 2), total_top - 9, str(total[1]))
    return bottom


def _draw_signatures(pdf, width, bottom):
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(0, bottom - 12, "+1 means next day. Higher offsets count calendar days.")
    certification = (
        "I certify on my honor that this record accurately shows",
        "the hours I logged daily on arrival at and departure from work.",
    )
    for index, line in enumerate(certification):
        pdf.drawString(0, bottom - 31 - 10 * index, line)

    signature_left = width * 0.13
    signature_right = width - signature_left
    pdf.line(signature_left, bottom - 72, signature_right, bottom - 72)
    pdf.drawCentredString(width / 2, bottom - 83, "Employee Signature")
    pdf.drawString(0, bottom - 108, "Verified as to the prescribed office hours")
    pdf.line(signature_left, bottom - 138, signature_right, bottom - 138)
    pdf.drawCentredString(width / 2, bottom - 149, "In-Charge")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawCentredString(width / 2, bottom - 175, "KlockIN by Tomeku")


def render_dtr_pdf(employee, month, last_day, rows, intervals, use_first_last):
    days, total = _monthly_cells(last_day, rows, intervals, use_first_last)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(f"KlockIN | Daily time record | {month:%B %Y}")
    pdf.setAuthor("Tomeku")
    pdf.setCreator("KlockIN")
    page_width, page_height = A4
    width = (page_width - 2 * MARGIN - GUTTER) / 2

    for left in (MARGIN, MARGIN + width + GUTTER):
        pdf.saveState()
        pdf.translate(left, 0)
        pdf.setLineWidth(0.45)
        _draw_header(pdf, employee, month, width)
        bottom = _draw_grid(pdf, days, total, width, use_first_last)
        _draw_signatures(pdf, width, bottom)
        pdf.restoreState()

    pdf.setStrokeGray(0.7)
    pdf.setLineWidth(0.4)
    pdf.setDash(2, 3)
    pdf.line(page_width / 2, 62, page_width / 2, page_height - 21)
    pdf.save()
    output.seek(0)
    return FileResponse(
        output,
        as_attachment=True,
        filename=f"KlockIN-DTR-{employee.pk}-{month:%Y-%m}.pdf",
        content_type="application/pdf",
    )
