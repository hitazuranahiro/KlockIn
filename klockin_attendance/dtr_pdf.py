from io import BytesIO
from xml.sax.saxutils import escape

from django.http import FileResponse
from django.utils import timezone
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from attendance.corrections import CORRECTION_PREFIX, MISSED_PUNCH_CORRECTION_PREFIX
from attendance.methods.utils import strtime_seconds


MARGIN = 26
GUTTER = 22
TABLE_TOP = 704
ROW_HEIGHT = 13
NOTE_STYLE = ParagraphStyle("DTR note", fontName="Helvetica", fontSize=7.5, leading=9)


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

    # Approved missed punches update the activity too. A direct daily
    # override takes precedence over the underlying activity clock times.
    if not activities or row.history.filter(
        history_change_reason__startswith=CORRECTION_PREFIX
    ).exclude(
        history_change_reason__startswith=MISSED_PUNCH_CORRECTION_PREFIX
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


def _fit_line(value, font, size, width):
    if stringWidth(value, font, size) <= width:
        return value
    prefix = value
    while prefix and stringWidth(prefix + "…", font, size) > width:
        prefix = prefix[:-1]
    return prefix.rstrip() + "…"


def _draw_header(pdf, employee, month, width, company_name):
    pdf.setFont("Helvetica", 8)
    pdf.drawString(0, 816, "CS Form No. 48 style")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(width / 2, 796, "DAILY TIME RECORD")
    if company_name:
        pdf.setFont("Helvetica", 8.5)
        pdf.drawCentredString(
            width / 2, 784, _fit_line(company_name, "Helvetica", 8.5, width)
        )

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


def _draw_grid(
    pdf, days, total, width, use_first_last, *, table_top, row_height, show_undertime
):
    clock_count = 2 if use_first_last else 4
    day_width = 23
    hours_width = 28
    minutes_width = 33
    times_end = width - (hours_width + minutes_width if show_undertime else 0)
    clock_width = (times_end - day_width) / clock_count
    columns = [
        0,
        *(day_width + index * clock_width for index in range(clock_count + 1)),
    ]
    if show_undertime:
        columns.extend((width - minutes_width, width))
    split_header = table_top - row_height
    days_top = split_header - row_height
    total_top = days_top - len(days) * row_height
    bottom = total_top - row_height if show_undertime else total_top
    text_offset = min(9, row_height * 0.78)
    clock_end = clock_count + 1

    for index, x in enumerate(columns):
        y = bottom if index == 0 or index >= clock_end else total_top
        splits_undertime = show_undertime and index == clock_end + 1
        splits_clock = not use_first_last and index in (2, 4)
        pdf.line(x, split_header if splits_undertime or splits_clock else table_top, x, y)
    pdf.line(0, table_top, width, table_top)
    if not use_first_last or show_undertime:
        pdf.line(times_end if use_first_last else day_width, split_header, width, split_header)
    for row in range(len(days) + (2 if show_undertime else 1)):
        y = days_top - row * row_height
        pdf.line(0, y, width, y)

    def center(index):
        return (columns[index] + columns[index + 1]) / 2

    pdf.setFont("Helvetica-Bold", 7.5)
    combined_header_text = table_top - (row_height + 3)
    first_header_text = table_top - text_offset
    second_header_text = split_header - text_offset
    pdf.drawCentredString(center(0), combined_header_text, "Day")
    if use_first_last:
        pdf.drawCentredString(center(1), combined_header_text, "First In")
        pdf.drawCentredString(center(2), combined_header_text, "Last Out")
    else:
        pdf.drawCentredString(columns[2], first_header_text, "A.M.")
        pdf.drawCentredString(columns[4], first_header_text, "P.M.")
        for index, label in enumerate(("Arrival", "Departure", "Arrival", "Departure"), 1):
            pdf.drawCentredString(center(index), second_header_text, label)
    if show_undertime:
        pdf.drawCentredString((times_end + width) / 2, first_header_text, "UNDERTIME")
        pdf.drawCentredString(center(clock_end), second_header_text, "Hours")
        pdf.drawCentredString(center(clock_end + 1), second_header_text, "Minutes")

    pdf.setFont("Helvetica", 8)
    for index, values in enumerate(days):
        y = days_top - index * row_height - text_offset
        for column, value in enumerate(values if show_undertime else values[:-2]):
            pdf.drawCentredString(center(column), y, str(value))

    if show_undertime:
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawCentredString(times_end / 2, total_top - text_offset, "TOTAL")
        pdf.drawCentredString(center(clock_end), total_top - text_offset, str(total[0]))
        pdf.drawCentredString(center(clock_end + 1), total_top - text_offset, str(total[1]))
    return bottom


def _draw_signatures(pdf, width, bottom, *, compact, note):
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(0, bottom - 12, "+1 means next day. Higher offsets count calendar days.")
    if note:
        display_note = escape(" ".join(note.split()))
        paragraph = Paragraph(f"Notes: {display_note}", NOTE_STYLE)
        _, note_height = paragraph.wrap(width, bottom)
        paragraph.drawOn(pdf, 0, bottom - 17 - note_height)
        bottom -= 4 + note_height
    certification = (
        "I certify on my honor that this record accurately shows",
        "the hours I logged daily on arrival at and departure from work.",
    )
    for index, line in enumerate(certification):
        pdf.drawString(0, bottom - 31 - 10 * index, line)

    if compact:
        right = width / 2 + 15
        signature_y = bottom - 62
        pdf.drawString(right, bottom - 31, "Verified as to the prescribed office hours")
        pdf.line(0, signature_y, width / 2 - 15, signature_y)
        pdf.line(right, signature_y, width, signature_y)
        pdf.drawCentredString((width / 2 - 15) / 2, signature_y - 11, "Employee Signature")
        pdf.drawCentredString((right + width) / 2, signature_y - 11, "In-Charge")
        pdf.setFont("Helvetica", 6.5)
        pdf.drawCentredString(width / 2, bottom - 91, "KlockIN by Tomeku")
        return

    signature_left = width * 0.13
    signature_right = width - signature_left
    pdf.line(signature_left, bottom - 72, signature_right, bottom - 72)
    pdf.drawCentredString(width / 2, bottom - 83, "Employee Signature")
    pdf.drawString(0, bottom - 108, "Verified as to the prescribed office hours")
    pdf.line(signature_left, bottom - 138, signature_right, bottom - 138)
    pdf.drawCentredString(width / 2, bottom - 149, "In-Charge")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawCentredString(width / 2, bottom - 175, "KlockIN by Tomeku")


def render_dtr_pdf(
    employee, month, last_day, rows, intervals, use_first_last, *,
    orientation="portrait", company_name="", show_undertime=True, note="", preview=False,
):
    days, total = _monthly_cells(last_day, rows, intervals, use_first_last)
    compact = orientation == "landscape"
    page_size = landscape(A4) if compact else A4
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=page_size)
    pdf.setTitle(f"KlockIN | Daily time record | {month:%B %Y}")
    pdf.setAuthor("Tomeku")
    pdf.setCreator("KlockIN")
    page_width, page_height = page_size
    header_offset = page_height - A4[1]
    width = page_width - 2 * MARGIN if compact else (page_width - 2 * MARGIN - GUTTER) / 2
    copies = (MARGIN,) if compact else (MARGIN, MARGIN + width + GUTTER)

    for left in copies:
        pdf.saveState()
        pdf.translate(left, 0)
        pdf.setLineWidth(0.45)
        pdf.saveState()
        pdf.translate(0, header_offset)
        _draw_header(pdf, employee, month, width, company_name)
        pdf.restoreState()
        bottom = _draw_grid(
            pdf, days, total, width, use_first_last,
            table_top=TABLE_TOP + header_offset,
            row_height=9.5 if compact else ROW_HEIGHT,
            show_undertime=show_undertime,
        )
        _draw_signatures(pdf, width, bottom, compact=compact, note=note)
        pdf.restoreState()

    if not compact:
        pdf.setStrokeGray(0.7)
        pdf.setLineWidth(0.4)
        pdf.setDash(2, 3)
        pdf.line(page_width / 2, 62, page_width / 2, page_height - 21)
    pdf.save()
    output.seek(0)
    return FileResponse(
        output,
        as_attachment=not preview,
        filename=f"KlockIN-DTR-{employee.pk}-{month:%Y-%m}.pdf",
        content_type="application/pdf",
    )
