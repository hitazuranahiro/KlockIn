"""
Demo-data helpers for role (user group) assignments.

Groups are created by post_migrate (see base.signals._DEFAULT_HRMS_GROUPS),
so membership is applied by group *name* after fixtures load — never by PK.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import Group
from django.db import transaction

from base.demo_data.identity import DEMO_EMAIL_DOMAIN, legacy_demo_email
from base.models import Company, CompanyGroupAssignment
from klockin_auth.models import HorillaUser

logger = logging.getLogger(__name__)

# (user email, group name, company name)
# Keep this small — enough to demo Roles & Permissions and company-scoped access.
DEMO_ROLE_ASSIGNMENTS = (
    (f"alexander.smith@{DEMO_EMAIL_DOMAIN}", "Asset Manager", "Your Company"),
    (f"alexander.smith@{DEMO_EMAIL_DOMAIN}", "Asset Manager", "Your Company Inc."),
    (f"michael.brown@{DEMO_EMAIL_DOMAIN}", "HR Manager", "Your Company"),
    (f"sarah.anderson@{DEMO_EMAIL_DOMAIN}", "Payroll Manager", "Your Company"),
    (f"emily.clark@{DEMO_EMAIL_DOMAIN}", "Leave Manager", "Your Company"),
    (f"jessica.evans@{DEMO_EMAIL_DOMAIN}", "Attendance Manager", "Your Company"),
    (f"benjamin.parker@{DEMO_EMAIL_DOMAIN}", "Recruiter", "Your Company Ltd."),
    (f"lily.campbell@{DEMO_EMAIL_DOMAIN}", "Helpdesk Agent", "Your Company Inc."),
    (f"matthew.harris@{DEMO_EMAIL_DOMAIN}", "Performance Manager", "Your Company"),
    (f"david.king@{DEMO_EMAIL_DOMAIN}", "Project Manager", "Your Company"),
)

DEMO_PROTECTED_EMAILS = frozenset(
    address
    for email, _, _ in DEMO_ROLE_ASSIGNMENTS
    for address in (email, legacy_demo_email(email))
)


@transaction.atomic
def assign_demo_user_groups():
    """
    Assign a few demo employees to default HRMS roles.

    Safe to call repeatedly (get_or_create). Skips missing users/groups/companies.
    Syncs ``user.groups`` so legacy (non-scoped) mode still works.
    """
    created = 0
    for email, group_name, company_name in DEMO_ROLE_ASSIGNMENTS:
        user = None
        for address in (email, legacy_demo_email(email)):
            user = (
                HorillaUser.objects.filter(email=address).first()
                or HorillaUser.objects.filter(username=address).first()
            )
            if user:
                break
        group = Group.objects.filter(name=group_name).first()
        company = Company.objects.filter(company=company_name).first()
        if not user or not group or not company:
            logger.debug(
                "Skipping demo role assignment %s / %s / %s (missing user=%s group=%s company=%s)",
                email,
                group_name,
                company_name,
                bool(user),
                bool(group),
                bool(company),
            )
            continue
        _, was_created = CompanyGroupAssignment.objects.get_or_create(
            user=user,
            group=group,
            company=company,
        )
        CompanyGroupAssignment.sync_user_group_membership(user, group)
        if was_created:
            created += 1
    return created
