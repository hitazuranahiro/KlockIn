"""Export filtered Timekeeping reports through the shared report renderers."""
from django.shortcuts import render
from django.utils import timezone

from attendance.methods.utils import format_time, strtime_seconds
from report.company_context import company_letterhead
from report.export import export_csv, export_pdf, export_xlsx
from report.personalization import log_report_run


QUEUE_NOTE = (
    "Counts reflect each phone's last report. Punches that remain on a disconnected "
    "phone are unavailable to the server."
)
EMPLOYEE_COLUMNS = (("employee", "Employee"), ("badge", "Badge ID"))
FORMATS = {"csv": export_csv, "xlsx": export_xlsx, "pdf": export_pdf}


def _employee_row(employee):
    return {"employee": employee.get_full_name(), "badge": employee.badge_id or ""}


def _timestamp(value):
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S %Z") if value else ""


def _report_table(report, records, include_device):
    if report == "summary":
        columns = (
            ("present", "Present days"), ("absent", "Absences"), ("late", "Late days"),
            ("worked", "Recorded work"), ("undertime", "Undertime"), ("overtime", "Overtime"),
        )
        rows = [{**record, **_employee_row(record["employee"])} for record in records]
    elif report == "unsynced":
        columns = (("pending", "Reported pending"), ("observed", "Observed on device"),
                   ("reported", "Received by server"))
        rows = [
            {**_employee_row(device.employee),
             "device": device.device_fingerprint if include_device else "",
             "pending": device.pending_punches if device.pending_punches is not None else "Unknown",
             "observed": _timestamp(device.queue_observed_at),
             "reported": _timestamp(device.queue_reported_at)}
            for device in records
        ]
    elif report == "pending":
        columns = (("punch", "Punch"), ("captured", "Punch time"),
                   ("received", "Received by server"), ("source", "Source"))
        rows = [
            {**_employee_row(punch.employee), "punch": punch.get_punch_type_display(),
             "captured": _timestamp(punch.punched_at), "received": _timestamp(punch.server_receive_timestamp),
             "source": punch.get_source_display(),
             "device": punch.device_fingerprint if include_device else ""}
            for punch in records
        ]
    elif report == "absent":
        columns = (("date", "Date"), ("status", "Status"))
        rows = [
            {**_employee_row(record.employee_id), "date": record.date.isoformat(),
             "status": record.get_work_record_type_display()}
            for record in records
        ]
    else:
        columns = (("date", "Work date"), ("first", "First in"), ("last", "Last out"),
                   ("worked", "Worked"), ("undertime", "Undertime"), ("overtime", "Overtime"))
        rows = []
        for day in records:
            deficit = ""
            if day.attendance_clock_out and day.minimum_hour:
                minimum = strtime_seconds(day.minimum_hour)
                worked = day.at_work_second if day.at_work_second is not None else strtime_seconds(
                    day.attendance_worked_hour or "00:00"
                )
                deficit = format_time(max(0, minimum - worked))
            rows.append({
                **_employee_row(day.employee_id), "date": day.attendance_date.isoformat(),
                "first": day.attendance_clock_in.isoformat() if day.attendance_clock_in is not None else "",
                "last": day.attendance_clock_out.isoformat() if day.attendance_clock_out is not None else "",
                "worked": day.attendance_worked_hour, "undertime": deficit,
                "overtime": day.attendance_overtime,
            })
    if include_device and report in {"unsynced", "pending"}:
        columns += (("device", "Device fingerprint"),)
    return EMPLOYEE_COLUMNS + columns, rows


def report_response(request, report, title, records, filters, export_format, *, include_device):
    columns, rows = _report_table(report, records, include_device)
    start, end = filters["start"].isoformat(), filters["end"].isoformat()
    note = QUEUE_NOTE if report == "unsynced" else ""
    slug = f"timekeeping-{report or 'daily'}"
    log_report_run(request, slug, "export", {
        "format": export_format, "start": start, "end": end,
        "employee": filters["employee"].pk if filters["employee"] else None,
        "department": filters["department"],
    })
    if export_format == "print":
        return render(request, "klockin_attendance/report_print.html", {
            "title": title, "start": start, "end": end, "note": note,
            "headers": [label for _, label in columns],
            "rows": [[row[key] for key, _ in columns] for row in rows],
        })
    payload = {
        "title": title,
        "period": {"from_date": start, "to_date": end},
        "table": {"columns": [{"key": key, "label": label} for key, label in columns], "rows": rows},
    }
    meta = {
        "company": company_letterhead(request), "user": request.user.get_full_name() or request.user.get_username(),
        "product_name": "KlockIN · Timekeeping",
    }
    if note:
        meta.update(filters_label=note, filters_pairs=[("Queue visibility", note)])
    return FORMATS[export_format](payload, filename=f"KlockIN-{slug}.{export_format}", meta=meta)
