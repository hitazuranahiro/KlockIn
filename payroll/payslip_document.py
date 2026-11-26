"""The same issued payroll figures for every payslip document layout."""

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.http import content_disposition_header

from base.models import Company
from klockin.export_preferences import EXPORT_DEFAULTS, resolve_export_options
from klockin.pdf import document_pdf


def render_payslip_document(request, payslip, *, html=False, filename="payslip.pdf", use_preferences=True):
    options = (
        resolve_export_options(request.user, "payslip", request.GET)
        if use_preferences else EXPORT_DEFAULTS["payslip"]
    )
    employee = payslip.employee_id
    company = employee.get_company() or Company.objects.filter(hq=True).first()
    snapshot = payslip.pay_head_data if isinstance(payslip.pay_head_data, dict) else {}
    start, end = payslip.start_date, payslip.end_date
    context = {
        "contract_wage": payslip.contract_wage,
        "basic_pay": payslip.basic_pay,
        "gross_pay": payslip.gross_pay,
        "total_deductions": payslip.deduction,
        "net_pay": payslip.net_pay,
        **snapshot,
        "employee": employee,
        "company": company,
        "payslip": payslip,
        "month_start_name": start.strftime("%B %d, %Y"),
        "month_end_name": end.strftime("%B %d, %Y"),
        "total_calendar_days": (end - start).days + 1,
        "export_options": options,
        "pdf_output": not html,
    }
    markup = render_to_string("payroll/payslip/payslip_pdf.html", context)
    if html:
        response = HttpResponse(markup, content_type="text/html; charset=utf-8")
        response["Cache-Control"] = "private, no-store"
        return response

    response = document_pdf(markup, filename, host=request.get_host())
    download = use_preferences and request.GET.get("download") == "1" and request.GET.get("preview") != "1"
    if response.status_code == 200 and download:
        response["Content-Disposition"] = content_disposition_header(True, filename)
    return response
