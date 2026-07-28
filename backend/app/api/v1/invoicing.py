"""Organization-scoped invoicing reads with legacy-compatible response shapes."""

import calendar
import json
import smtplib
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from email.message import EmailMessage
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from sqlalchemy import delete, func, insert, or_, select, update

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Base

router = APIRouter(prefix="/invoicing", tags=["invoicing"])
tables = Base.metadata.tables
ZERO = Decimal("0")


def _advance_recurring_date(value: date, frequency: str) -> date:
    if frequency == "weekly":
        return value + timedelta(days=7)
    if frequency == "bi_weekly":
        return value + timedelta(days=14)
    months = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(frequency, 1)
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )


def _organization_id(current_user: CurrentUser) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An organization is required for invoicing",
        )
    return current_user.organization_id


def _invoice_rows(
    current_user: CurrentUser,
    session: SessionDependency,
    *,
    invoice_status: str | None = None,
    family_id: UUID | None = None,
    recipient_id: UUID | None = None,
    search: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    invoices = tables["invoices"]
    statement = select(invoices).where(invoices.c.organization_id == _organization_id(current_user))
    if invoice_status:
        statement = statement.where(invoices.c.status == invoice_status)
    if family_id:
        statement = statement.where(invoices.c.family_id == family_id)
    if recipient_id:
        statement = statement.where(invoices.c.recipient_id == recipient_id)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                invoices.c.invoice_number.ilike(pattern),
                invoices.c.client_name.ilike(pattern),
                invoices.c.file_number.ilike(pattern),
            )
        )
    if from_date:
        statement = statement.where(invoices.c.issue_date >= from_date)
    if to_date:
        statement = statement.where(invoices.c.issue_date <= to_date)
    return list(session.execute(statement).mappings())


def _enrich_invoices(rows, session: SessionDependency) -> list[dict]:
    if not rows:
        return []
    invoice_ids = [row["id"] for row in rows]
    family_ids = {row["family_id"] for row in rows if row["family_id"]}
    recipient_ids = {row["recipient_id"] for row in rows if row["recipient_id"]}
    families = tables["families"]
    funding_sources = tables["funding_sources"]
    line_items = tables["invoice_line_items"]
    family_map = (
        {
            row["id"]: dict(row)
            for row in session.execute(
                select(families.c.id, families.c.name).where(families.c.id.in_(family_ids))
            ).mappings()
        }
        if family_ids
        else {}
    )
    recipient_map = (
        {
            row["id"]: dict(row)
            for row in session.execute(
                select(
                    funding_sources.c.id,
                    funding_sources.c.name,
                    funding_sources.c.contact_name,
                    funding_sources.c.contact_email,
                ).where(funding_sources.c.id.in_(recipient_ids))
            ).mappings()
        }
        if recipient_ids
        else {}
    )
    item_map: dict[UUID, list[dict]] = defaultdict(list)
    for row in session.execute(
        select(line_items)
        .where(line_items.c.invoice_id.in_(invoice_ids))
        .order_by(line_items.c.created_at)
    ).mappings():
        item_map[row["invoice_id"]].append(dict(row))
    return [
        {
            **dict(row),
            "family": family_map.get(row["family_id"]),
            "recipient": recipient_map.get(row["recipient_id"]),
            "line_items": item_map.get(row["id"], []),
        }
        for row in rows
    ]


def _get_invoice_row(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
):
    invoices = tables["invoices"]
    row = (
        session.execute(
            select(invoices).where(
                invoices.c.id == invoice_id,
                invoices.c.organization_id == _organization_id(current_user),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return row


def _provider_settings_row(current_user: CurrentUser, session: SessionDependency):
    provider_settings = tables["provider_settings"]
    return (
        session.execute(
            select(provider_settings).where(
                provider_settings.c.organization_id == _organization_id(current_user)
            )
        )
        .mappings()
        .first()
    )


def _next_invoice_number(current_user: CurrentUser, session: SessionDependency) -> str:
    provider_settings = tables["provider_settings"]
    row = _provider_settings_row(current_user, session)
    if row is None:
        return f"INV-{date.today():%Y%m%d}-{str(uuid4())[:8]}"
    next_number = row["next_invoice_number"]
    prefix = row["invoice_prefix"] or "INV-"
    separator = "" if prefix.endswith(("-", "/")) else "-"
    session.execute(
        update(provider_settings)
        .where(provider_settings.c.id == row["id"])
        .values(next_invoice_number=next_number + 1)
    )
    return f"{prefix}{separator}{next_number:05d}"


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _validate_invoice_dates(payload: dict) -> None:
    try:
        issue_date = date.fromisoformat(payload["issue_date"])
        due_date = date.fromisoformat(payload["due_date"])
        period_start = (
            date.fromisoformat(payload["period_start"]) if payload.get("period_start") else None
        )
        period_end = (
            date.fromisoformat(payload["period_end"]) if payload.get("period_end") else None
        )
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valid issue and due dates are required",
        ) from None
    if due_date < issue_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Due date cannot be before the issue date",
        )
    if period_start and period_end and period_end < period_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Billing period end cannot be before its start",
        )


def _invoice_totals(payload: dict, amount_paid: Decimal = ZERO) -> dict[str, Decimal]:
    subtotal = sum((_money(item.get("amount")) for item in payload.get("line_items", [])), ZERO)
    discount_percentage = _money(payload.get("discount_percentage"))
    discount_amount = (
        (subtotal * discount_percentage / Decimal("100")).quantize(Decimal("0.01"))
        if discount_percentage
        else _money(payload.get("discount_amount"))
    )
    taxable = max(ZERO, subtotal - discount_amount)
    tax_rate = _money(payload.get("tax_rate"))
    tax_amount = (taxable * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
    total = taxable + tax_amount
    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total_amount": total,
        "balance_due": max(ZERO, total - amount_paid),
    }


def _invoice_payload_values(payload: dict) -> dict:
    values = {
        key: payload.get(key)
        for key in {
            "client_name",
            "client_email",
            "client_address",
            "file_number",
            "status",
            "notes",
            "terms",
            "discount_percentage",
        }
        if key in payload
    }
    for key in {"family_id", "guardian_id", "recipient_id"}:
        if key in payload:
            values[key] = UUID(payload[key]) if payload.get(key) else None
    for key in {"issue_date", "due_date", "period_start", "period_end"}:
        if key in payload:
            values[key] = date.fromisoformat(payload[key]) if payload.get(key) else None
    return values


def _replace_line_items(invoice_id: UUID, payload: dict, session: SessionDependency) -> None:
    line_items = tables["invoice_line_items"]
    session.execute(delete(line_items).where(line_items.c.invoice_id == invoice_id))
    for item in payload.get("line_items", []):
        session.execute(
            insert(line_items).values(
                id=uuid4(),
                invoice_id=invoice_id,
                item_type=item.get("item_type") or "service_flat",
                description=item.get("description") or "Invoice item",
                child_id=UUID(item["child_id"]) if item.get("child_id") else None,
                child_name=item.get("child_name"),
                full_rate=item.get("full_rate"),
                subsidy_amount=item.get("subsidy_amount"),
                hours=item.get("hours"),
                hourly_rate=item.get("hourly_rate"),
                quantity=item.get("quantity") or 1,
                unit_price=item.get("unit_price"),
                amount=_money(item.get("amount")),
            )
        )


@router.get("/invoices")
def list_invoices(
    current_user: CurrentUser,
    session: SessionDependency,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=500),
    invoice_status: str | None = Query(None, alias="status"),
    family_id: UUID | None = None,
    recipient_id: UUID | None = None,
    search: str | None = None,
) -> dict:
    rows = _invoice_rows(
        current_user,
        session,
        invoice_status=invoice_status,
        family_id=family_id,
        recipient_id=recipient_id,
        search=search,
    )
    rows.sort(key=lambda row: (row["issue_date"], row["created_at"]), reverse=True)
    offset = (page - 1) * limit
    return {
        "items": _enrich_invoices(rows[offset : offset + limit], session),
        "total": len(rows),
        "page": page,
        "limit": limit,
        "has_more": offset + limit < len(rows),
    }


@router.get("/invoices/dashboard")
def invoice_dashboard(
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    rows = _invoice_rows(current_user, session)
    today = date.today()
    month_start = today.replace(day=1)
    total_outstanding = sum((row["balance_due"] or ZERO for row in rows), ZERO)
    total_overdue = sum(
        (
            row["balance_due"] or ZERO
            for row in rows
            if row["due_date"] < today and row["status"] not in {"paid", "void", "cancelled"}
        ),
        ZERO,
    )
    payments = tables["payments"]
    invoices = tables["invoices"]
    paid_this_month = (
        session.scalar(
            select(func.coalesce(func.sum(payments.c.amount), 0))
            .select_from(payments.join(invoices, payments.c.invoice_id == invoices.c.id))
            .where(
                invoices.c.organization_id == _organization_id(current_user),
                payments.c.payment_date >= month_start,
                payments.c.payment_date <= today,
            )
        )
        or ZERO
    )
    recent = sorted(rows, key=lambda row: row["created_at"], reverse=True)[:5]
    return {
        "total_invoiced": sum((row["total_amount"] or ZERO for row in rows), ZERO),
        "total_collected": sum((row["amount_paid"] or ZERO for row in rows), ZERO),
        "total_outstanding": total_outstanding,
        "total_overdue": total_overdue,
        "paid_this_month": paid_this_month,
        "invoice_count": len(rows),
        "invoices_count": len(rows),
        "recent_invoices": _enrich_invoices(recent, session),
    }


@router.get("/invoices/analytics")
def invoice_analytics(
    current_user: CurrentUser,
    session: SessionDependency,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    rows = _invoice_rows(
        current_user,
        session,
        from_date=from_date,
        to_date=to_date,
    )
    today = date.today()
    payments = tables["payments"]
    invoices = tables["invoices"]
    payment_statement = (
        select(payments, invoices.c.family_id)
        .select_from(payments.join(invoices, payments.c.invoice_id == invoices.c.id))
        .where(invoices.c.organization_id == _organization_id(current_user))
    )
    if from_date:
        payment_statement = payment_statement.where(payments.c.payment_date >= from_date)
    if to_date:
        payment_statement = payment_statement.where(payments.c.payment_date <= to_date)
    payment_rows = list(session.execute(payment_statement).mappings())

    monthly: dict[str, dict] = defaultdict(
        lambda: {"revenue": ZERO, "invoices_count": 0, "payments_count": 0}
    )
    for row in rows:
        bucket = monthly[row["issue_date"].strftime("%Y-%m")]
        bucket["revenue"] += row["total_amount"] or ZERO
        bucket["invoices_count"] += 1
    for row in payment_rows:
        monthly[row["payment_date"].strftime("%Y-%m")]["payments_count"] += 1

    family_totals: dict[UUID | None, dict] = defaultdict(
        lambda: {"total_revenue": ZERO, "invoices_count": 0, "outstanding": ZERO}
    )
    for row in rows:
        totals = family_totals[row["family_id"]]
        totals["total_revenue"] += row["amount_paid"] or ZERO
        totals["invoices_count"] += 1
        totals["outstanding"] += row["balance_due"] or ZERO
    family_ids = {family_id for family_id in family_totals if family_id}
    families = tables["families"]
    family_names = (
        dict(
            session.execute(
                select(families.c.id, families.c.name).where(families.c.id.in_(family_ids))
            ).all()
        )
        if family_ids
        else {}
    )

    status_totals: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_amount": ZERO})
    for row in rows:
        status_total = status_totals[row["status"]]
        status_total["count"] += 1
        status_total["total_amount"] += row["total_amount"] or ZERO

    payment_dates: dict[UUID, date] = {}
    for payment in payment_rows:
        current = payment_dates.get(payment["invoice_id"])
        if current is None or payment["payment_date"] > current:
            payment_dates[payment["invoice_id"]] = payment["payment_date"]
    days_to_pay = [
        (payment_dates[row["id"]] - row["issue_date"]).days
        for row in rows
        if row["id"] in payment_dates and row["status"] == "paid"
    ]

    total_revenue = sum((row["amount"] or ZERO for row in payment_rows), ZERO)
    total_outstanding = sum((row["balance_due"] or ZERO for row in rows), ZERO)
    return {
        "total_revenue": total_revenue,
        "total_outstanding": total_outstanding,
        "total_overdue": sum(
            (
                row["balance_due"] or ZERO
                for row in rows
                if row["due_date"] < today and row["status"] not in {"paid", "void", "cancelled"}
            ),
            ZERO,
        ),
        "average_invoice_value": (
            sum((row["total_amount"] or ZERO for row in rows), ZERO) / len(rows) if rows else ZERO
        ),
        "average_days_to_pay": sum(days_to_pay) / len(days_to_pay) if days_to_pay else 0,
        "revenue_by_month": [
            {"period": period, **values} for period, values in sorted(monthly.items())
        ],
        "top_clients": sorted(
            (
                {
                    "family_id": family_id,
                    "family_name": family_names.get(family_id, "Unassigned client"),
                    **values,
                }
                for family_id, values in family_totals.items()
            ),
            key=lambda item: item["total_revenue"],
            reverse=True,
        )[:10],
        "status_breakdown": [
            {"status": invoice_status, **values}
            for invoice_status, values in sorted(status_totals.items())
        ],
    }


@router.get("/parent-portion-tracker")
def parent_portion_tracker(
    current_user: CurrentUser,
    session: SessionDependency,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    today = date.today()
    start = from_date or today.replace(day=1)
    end = to_date or today
    families_table = tables["families"]
    children_table = tables["children"]
    guardians = tables["guardians"]
    invoices = tables["invoices"]
    line_items = tables["invoice_line_items"]
    payments = tables["payments"]
    child_funding = tables["child_funding"]
    funding_sources = tables["funding_sources"]
    family_rows = list(
        session.execute(
            select(families_table).where(
                families_table.c.organization_id == _organization_id(current_user),
                families_table.c.status == "active",
            )
        ).mappings()
    )
    invoice_rows = list(
        session.execute(
            select(invoices).where(
                invoices.c.organization_id == _organization_id(current_user),
                invoices.c.issue_date >= start,
                invoices.c.issue_date <= end,
            )
        ).mappings()
    )
    invoice_ids = [row["id"] for row in invoice_rows]
    item_rows = (
        list(
            session.execute(
                select(line_items).where(line_items.c.invoice_id.in_(invoice_ids))
            ).mappings()
        )
        if invoice_ids
        else []
    )
    payment_rows = (
        list(
            session.execute(
                select(payments).where(payments.c.invoice_id.in_(invoice_ids))
            ).mappings()
        )
        if invoice_ids
        else []
    )
    invoices_by_family: dict[UUID, list] = defaultdict(list)
    items_by_invoice: dict[UUID, list] = defaultdict(list)
    payments_by_invoice: dict[UUID, list] = defaultdict(list)
    for row in invoice_rows:
        if row["family_id"]:
            invoices_by_family[row["family_id"]].append(row)
    for row in item_rows:
        items_by_invoice[row["invoice_id"]].append(row)
    for row in payment_rows:
        payments_by_invoice[row["invoice_id"]].append(row)

    family_results = []
    payment_method_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"amount": ZERO, "count": 0}
    )
    funding_totals: dict[str, dict[str, Any]] = {}
    all_days_to_pay: list[int] = []
    aging_totals = [ZERO, ZERO, ZERO, ZERO]
    aging_counts = [0, 0, 0, 0]
    status_counts = defaultdict(int)
    total_charges = total_subsidy = total_parent_owed = total_parent_paid = ZERO

    for family in family_rows:
        family_invoices = invoices_by_family.get(family["id"], [])
        child_rows = list(
            session.execute(
                select(children_table).where(children_table.c.family_id == family["id"])
            ).mappings()
        )
        if not family_invoices and not child_rows:
            continue
        guardian = (
            session.execute(
                select(guardians)
                .where(guardians.c.family_id == family["id"])
                .order_by(guardians.c.guardian_type.asc())
            )
            .mappings()
            .first()
        )
        child_results = []
        family_charges = family_subsidy = ZERO
        family_funding_names: set[str] = set()
        for child in child_rows:
            child_items = [
                item
                for invoice in family_invoices
                for item in items_by_invoice[invoice["id"]]
                if item["child_id"] == child["id"]
            ]
            charges = sum((_money(item["amount"]) for item in child_items), ZERO)
            subsidy = sum((_money(item["subsidy_amount"]) for item in child_items), ZERO)
            parent = sum((_money(item["parent_portion"]) for item in child_items), ZERO)
            if parent == 0 and charges:
                parent = max(ZERO, charges - subsidy)
            funding_rows = list(
                session.execute(
                    select(child_funding, funding_sources.c.name, funding_sources.c.funding_type)
                    .select_from(
                        child_funding.join(
                            funding_sources,
                            child_funding.c.funding_source_id == funding_sources.c.id,
                        )
                    )
                    .where(
                        child_funding.c.child_id == child["id"], child_funding.c.is_active.is_(True)
                    )
                ).mappings()
            )
            names = list(dict.fromkeys(row["name"] for row in funding_rows))
            family_funding_names.update(names)
            for funding in funding_rows:
                entry = funding_totals.setdefault(
                    funding["name"],
                    {
                        "amount": ZERO,
                        "families": set(),
                        "children": set(),
                        "type": funding["funding_type"],
                    },
                )
                entry["amount"] += subsidy
                entry["families"].add(family["id"])
                entry["children"].add(child["id"])
            child_results.append(
                {
                    "child_id": child["id"],
                    "child_name": f"{child['first_name']} {child['last_name']}",
                    "age_group": child["age_group"],
                    "total_charges": charges,
                    "subsidy_amount": subsidy,
                    "parent_portion": parent,
                    "funding_sources": names,
                }
            )
            family_charges += charges
            family_subsidy += subsidy
        if family_charges == 0:
            family_charges = sum(
                (_money(invoice["total_amount"]) for invoice in family_invoices), ZERO
            )
            family_subsidy = sum(
                (
                    _money(item["subsidy_amount"])
                    for invoice in family_invoices
                    for item in items_by_invoice[invoice["id"]]
                ),
                ZERO,
            )
        family_parent_owed = max(ZERO, family_charges - family_subsidy)
        family_paid = ZERO
        methods: set[str] = set()
        days_to_pay: list[int] = []
        last_payment = None
        for invoice in family_invoices:
            for payment in payments_by_invoice[invoice["id"]]:
                amount = _money(payment["amount"])
                family_paid += amount
                method = payment["payment_method"]
                methods.add(method)
                payment_method_totals[method]["amount"] += amount
                payment_method_totals[method]["count"] += 1
                days = max(0, (payment["payment_date"] - invoice["issue_date"]).days)
                days_to_pay.append(days)
                all_days_to_pay.append(days)
                if last_payment is None or payment["payment_date"] > last_payment:
                    last_payment = payment["payment_date"]
        outstanding = max(ZERO, family_parent_owed - family_paid)
        family_aging = [ZERO, ZERO, ZERO, ZERO]
        for invoice in family_invoices:
            balance = _money(invoice["balance_due"])
            if balance <= 0 or invoice["status"] in {"paid", "cancelled", "void"}:
                continue
            days_past_due = max(0, (today - invoice["due_date"]).days)
            bucket = (
                0
                if days_past_due == 0
                else 1
                if days_past_due <= 30
                else 2
                if days_past_due <= 60
                else 3
            )
            family_aging[bucket] += balance
            aging_totals[bucket] += balance
            aging_counts[bucket] += 1
        payment_status = (
            "subsidy_only"
            if family_parent_owed == 0 and family_subsidy > 0
            else "paid"
            if outstanding == 0 and family_parent_owed > 0
            else "partial"
            if family_paid > 0
            else "unpaid"
        )
        status_counts[payment_status] += 1
        average_days = sum(days_to_pay) / len(days_to_pay) if days_to_pay else 0
        risk_score = 100
        if family_parent_owed:
            risk_score -= round(float(outstanding / family_parent_owed) * 30)
        risk_score -= (
            30 if family_aging[3] else 20 if family_aging[2] else 10 if family_aging[1] else 0
        )
        risk_score -= (
            20 if average_days > 60 else 10 if average_days > 30 else 5 if average_days > 14 else 0
        )
        if family_parent_owed > 0 and family_paid == 0:
            risk_score -= 20
        risk_score = max(0, min(100, risk_score))
        grade = (
            "A"
            if risk_score >= 90
            else "B"
            if risk_score >= 75
            else "C"
            if risk_score >= 60
            else "D"
            if risk_score >= 40
            else "F"
        )
        family_results.append(
            {
                "family_id": family["id"],
                "family_name": family["name"],
                "guardian_name": f"{guardian['first_name']} {guardian['last_name']}"
                if guardian
                else None,
                "guardian_email": guardian["email"] if guardian else None,
                "guardian_phone": guardian["cell_phone"] if guardian else None,
                "children": child_results,
                "total_charges": family_charges,
                "subsidy_amount": family_subsidy,
                "parent_portion_owed": family_parent_owed,
                "parent_portion_paid": family_paid,
                "outstanding": outstanding,
                "payment_status": payment_status,
                "risk_grade": grade,
                "risk_score": risk_score,
                "avg_days_to_pay": round(average_days),
                "payment_methods_used": sorted(methods),
                "funding_sources": sorted(family_funding_names),
                "invoices_count": len(family_invoices),
                "last_payment_date": last_payment,
                "aging_current": family_aging[0],
                "aging_30": family_aging[1],
                "aging_60": family_aging[2],
                "aging_90_plus": family_aging[3],
            }
        )
        total_charges += family_charges
        total_subsidy += family_subsidy
        total_parent_owed += family_parent_owed
        total_parent_paid += family_paid
    total_outstanding = max(ZERO, total_parent_owed - total_parent_paid)
    total_payment_amount = sum((entry["amount"] for entry in payment_method_totals.values()), ZERO)
    total_aging = sum(aging_totals, ZERO)
    aging_labels = ["Current", "1-30 Days", "31-60 Days", "90+ Days"]
    high_outstanding = [row for row in family_results if row["outstanding"] > 500]
    insights = []
    if high_outstanding:
        insights.append(
            {
                "type": "danger",
                "title": "High Outstanding Balances",
                "message": (
                    f"{len(high_outstanding)} families have outstanding parent portions over $500."
                ),
                "action": "send_reminders",
                "affected_count": len(high_outstanding),
            }
        )
    collection_rate = float(total_parent_paid / total_parent_owed * 100) if total_parent_owed else 0
    return {
        "families": sorted(family_results, key=lambda row: row["risk_score"]),
        "summary": {
            "total_charges": total_charges,
            "total_subsidy": total_subsidy,
            "total_parent_owed": total_parent_owed,
            "total_parent_paid": total_parent_paid,
            "total_outstanding": total_outstanding,
            "collection_rate": collection_rate,
            "avg_days_to_collect": round(sum(all_days_to_pay) / len(all_days_to_pay))
            if all_days_to_pay
            else 0,
            "families_count": len(family_results),
            "families_fully_paid": status_counts["paid"],
            "families_partial": status_counts["partial"],
            "families_unpaid": status_counts["unpaid"],
            "families_subsidy_only": status_counts["subsidy_only"],
            "prev_total_charges": 0,
            "prev_total_collected": 0,
            "prev_collection_rate": 0,
            "payment_method_breakdown": [
                {
                    "method": method,
                    "amount": entry["amount"],
                    "count": entry["count"],
                    "percentage": round(float(entry["amount"] / total_payment_amount * 100))
                    if total_payment_amount
                    else 0,
                }
                for method, entry in payment_method_totals.items()
            ],
            "funding_source_breakdown": [
                {
                    "source_name": name,
                    "source_type": entry["type"],
                    "amount": entry["amount"],
                    "families_count": len(entry["families"]),
                    "children_count": len(entry["children"]),
                }
                for name, entry in funding_totals.items()
            ],
            "aging_buckets": [
                {
                    "label": label,
                    "amount": aging_totals[index],
                    "count": aging_counts[index],
                    "percentage": round(float(aging_totals[index] / total_aging * 100))
                    if total_aging
                    else 0,
                }
                for index, label in enumerate(aging_labels)
            ],
            "smart_insights": insights,
            "waterfall": [
                {
                    "label": "Total Charges",
                    "value": total_charges,
                    "cumulative": total_charges,
                    "type": "total",
                },
                {
                    "label": "Subsidy Coverage",
                    "value": -total_subsidy,
                    "cumulative": total_parent_owed,
                    "type": "subtract",
                },
                {
                    "label": "Parent Portion",
                    "value": total_parent_owed,
                    "cumulative": total_parent_owed,
                    "type": "result",
                },
                {
                    "label": "Collected",
                    "value": -total_parent_paid,
                    "cumulative": total_outstanding,
                    "type": "subtract",
                },
                {
                    "label": "Outstanding",
                    "value": total_outstanding,
                    "cumulative": total_outstanding,
                    "type": "result",
                },
            ],
        },
    }


@router.get("/settings")
def get_invoice_settings(
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict | None:
    row = _provider_settings_row(current_user, session)
    if row is None:
        return None
    result = dict(row)
    result.pop("smtp_password", None)
    result["smtp_password_configured"] = bool(row["smtp_password"])
    return result


def _credit_row(credit_id: UUID, current_user: CurrentUser, session: SessionDependency):
    credits = tables["credit_notes"]
    row = (
        session.execute(
            select(credits).where(
                credits.c.id == credit_id,
                credits.c.organization_id == _organization_id(current_user),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit note not found")
    return row


def _enrich_credits(rows, session: SessionDependency) -> list[dict]:
    families = tables["families"]
    invoices = tables["invoices"]
    results = []
    for row in rows:
        family = (
            session.execute(
                select(families.c.id, families.c.name).where(families.c.id == row["family_id"])
            )
            .mappings()
            .first()
            if row["family_id"]
            else None
        )
        invoice = (
            session.execute(
                select(invoices.c.id, invoices.c.invoice_number).where(
                    invoices.c.id == row["invoice_id"]
                )
            )
            .mappings()
            .first()
            if row["invoice_id"]
            else None
        )
        results.append(
            {
                **dict(row),
                "family": dict(family) if family else None,
                "invoice": dict(invoice) if invoice else None,
            }
        )
    return results


@router.get("/credits")
def list_credit_notes(current_user: CurrentUser, session: SessionDependency) -> list[dict]:
    credits = tables["credit_notes"]
    rows = session.execute(
        select(credits)
        .where(credits.c.organization_id == _organization_id(current_user))
        .order_by(credits.c.created_at.desc())
    ).mappings()
    return _enrich_credits(rows, session)


@router.post("/credits", status_code=status.HTTP_201_CREATED)
def create_credit_note(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    credits = tables["credit_notes"]
    amount = _money(payload.get("amount"))
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Credit amount must be positive",
        )
    credit_id = uuid4()
    session.execute(
        insert(credits).values(
            id=credit_id,
            organization_id=_organization_id(current_user),
            credit_note_number=f"CN-{date.today():%Y%m%d}-{str(credit_id)[:8]}",
            issue_date=date.fromisoformat(payload.get("issue_date") or date.today().isoformat()),
            amount=amount,
            amount_applied=ZERO,
            balance=amount,
            reason=payload.get("reason") or "other",
            description=payload.get("description"),
            client_name=payload.get("client_name"),
            family_id=UUID(payload["family_id"]) if payload.get("family_id") else None,
            invoice_id=UUID(payload["invoice_id"]) if payload.get("invoice_id") else None,
            status="draft",
        )
    )
    session.commit()
    return _enrich_credits([_credit_row(credit_id, current_user, session)], session)[0]


@router.patch("/credits/{credit_id}/status")
def update_credit_status(
    credit_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    row = _credit_row(credit_id, current_user, session)
    new_status = payload.get("status")
    if new_status not in {"issued", "void"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid credit status"
        )
    session.execute(
        update(tables["credit_notes"])
        .where(tables["credit_notes"].c.id == row["id"])
        .values(status=new_status)
    )
    session.commit()
    return {"id": credit_id, "status": new_status}


@router.delete("/credits/{credit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credit_note(
    credit_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> None:
    _ensure_writable(request)
    row = _credit_row(credit_id, current_user, session)
    if row["amount_applied"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Applied credit notes cannot be deleted"
        )
    session.execute(delete(tables["credit_notes"]).where(tables["credit_notes"].c.id == row["id"]))
    session.commit()


@router.post("/credits/{credit_id}/apply", status_code=status.HTTP_201_CREATED)
def apply_credit_note(
    credit_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    credit = _credit_row(credit_id, current_user, session)
    invoice_id = UUID(payload["invoice_id"])
    invoice = _get_invoice_row(invoice_id, current_user, session)
    amount = min(_money(payload.get("amount")), credit["balance"], invoice["balance_due"])
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No credit can be applied"
        )
    new_credit_applied = credit["amount_applied"] + amount
    new_credit_balance = credit["balance"] - amount
    new_invoice_paid = invoice["amount_paid"] + amount
    new_invoice_balance = invoice["balance_due"] - amount
    credit_status = "fully_applied" if new_credit_balance == 0 else "partially_applied"
    invoice_status = "paid" if new_invoice_balance == 0 else "partial"
    session.execute(
        insert(tables["credit_applications"]).values(
            id=uuid4(),
            credit_note_id=credit_id,
            invoice_id=invoice_id,
            amount=amount,
            applied_date=date.today(),
        )
    )
    session.execute(
        update(tables["credit_notes"])
        .where(tables["credit_notes"].c.id == credit_id)
        .values(amount_applied=new_credit_applied, balance=new_credit_balance, status=credit_status)
    )
    session.execute(
        update(tables["invoices"])
        .where(tables["invoices"].c.id == invoice_id)
        .values(
            amount_paid=new_invoice_paid, balance_due=new_invoice_balance, status=invoice_status
        )
    )
    session.commit()
    return {"success": True, "amount": amount}


@router.patch("/settings")
def update_invoice_settings(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    provider_settings = tables["provider_settings"]
    editable = {
        "currency_symbol",
        "invoice_prefix",
        "default_tax_rate",
        "tax_name",
        "default_notes",
        "default_terms",
        "smtp_enabled",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_encryption",
        "smtp_from_email",
        "smtp_from_name",
    }
    unknown = set(payload) - editable
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown settings: {', '.join(sorted(unknown))}",
        )
    values = {key: value for key, value in payload.items() if key in editable}
    if values.get("smtp_password") == "":
        values.pop("smtp_password")
    row = _provider_settings_row(current_user, session)
    if row is None:
        session.execute(
            insert(provider_settings).values(
                id=uuid4(), organization_id=_organization_id(current_user), **values
            )
        )
    else:
        session.execute(
            update(provider_settings).where(provider_settings.c.id == row["id"]).values(**values)
        )
    session.commit()
    return get_invoice_settings(current_user, session)


@router.post("/settings/test-email")
def test_invoice_email_settings(
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    settings_row = _provider_settings_row(current_user, session)
    recipient = payload.get("test_email")
    if not settings_row or not recipient:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Saved SMTP settings and a test email address are required",
        )
    host, port = settings_row["smtp_host"], settings_row["smtp_port"]
    sender = settings_row["smtp_from_email"]
    if not host or not port or not sender:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="SMTP settings are incomplete"
        )
    message = EmailMessage()
    message["Subject"] = "CareSync SMTP test"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("Your CareSync email settings are working.")
    try:
        if settings_row["smtp_encryption"] == "ssl":
            smtp = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            smtp = smtplib.SMTP(host, port, timeout=20)
            if settings_row["smtp_encryption"] in {"tls", "starttls"}:
                smtp.starttls()
        with smtp:
            if settings_row["smtp_username"]:
                smtp.login(settings_row["smtp_username"], settings_row["smtp_password"] or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMTP test failed: {exc}",
        ) from exc
    return {"success": True, "message": "Test email sent successfully"}


@router.get("/prefill/{family_id}")
def prefilled_line_items(
    family_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
    as_of: date | None = None,
) -> dict:
    families = tables["families"]
    children = tables["children"]
    rates = tables["rate_schedules"]
    child_funding = tables["child_funding"]
    funding_sources = tables["funding_sources"]
    family = (
        session.execute(
            select(families).where(
                families.c.id == family_id,
                families.c.organization_id == _organization_id(current_user),
            )
        )
        .mappings()
        .first()
    )
    if family is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")
    child_rows = list(
        session.execute(
            select(children).where(
                children.c.family_id == family_id, children.c.is_active.is_(True)
            )
        ).mappings()
    )
    today = as_of or date.today()
    rate_rows = list(
        session.execute(
            select(rates).where(
                rates.c.organization_id == _organization_id(current_user),
                rates.c.is_active.is_(True),
                rates.c.effective_from <= today,
                or_(rates.c.effective_to.is_(None), rates.c.effective_to >= today),
            )
        ).mappings()
    )
    results = []
    for child in child_rows:
        matching_rates = [row for row in rate_rows if row["age_group"] == child["age_group"]]
        matching_rates.sort(key=lambda row: row["effective_from"], reverse=True)
        full_rate = _money(matching_rates[0]["rate_amount"] if matching_rates else 0)
        funding_rows = list(
            session.execute(
                select(child_funding, funding_sources.c.name.label("funding_name"))
                .select_from(
                    child_funding.join(
                        funding_sources,
                        child_funding.c.funding_source_id == funding_sources.c.id,
                    )
                )
                .where(
                    child_funding.c.child_id == child["id"],
                    child_funding.c.is_active.is_(True),
                    child_funding.c.effective_from <= today,
                    or_(
                        child_funding.c.effective_to.is_(None),
                        child_funding.c.effective_to >= today,
                    ),
                )
            ).mappings()
        )
        subsidy = ZERO
        for funding in funding_rows:
            if funding["coverage_type"] == "percentage":
                subsidy += full_rate * _money(funding["coverage_percentage"]) / Decimal("100")
            else:
                subsidy += _money(funding["coverage_amount"])
        subsidy = min(full_rate, subsidy.quantize(Decimal("0.01")))
        results.append(
            {
                "child_id": child["id"],
                "child_name": f"{child['first_name']} {child['last_name']}",
                "age_group": child["age_group"],
                "full_rate": full_rate,
                "subsidy": subsidy,
                "parent_portion": full_rate - subsidy,
                "funding_sources": [row["funding_name"] for row in funding_rows],
            }
        )
    return {
        "family_id": family_id,
        "family_name": family["name"],
        "children": results,
        "total_full_rate": sum((row["full_rate"] for row in results), ZERO),
        "total_subsidy": sum((row["subsidy"] for row in results), ZERO),
        "total_parent_portion": sum((row["parent_portion"] for row in results), ZERO),
    }


@router.post("/billing-runs/preview")
def preview_billing_run(
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _validate_invoice_dates(payload)
    if not payload.get("period_start") or not payload.get("period_end"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Billing period start and end are required",
        )
    organization_id = _organization_id(current_user)
    families = tables["families"]
    guardians = tables["guardians"]
    invoices = tables["invoices"]
    period_start = date.fromisoformat(payload["period_start"])
    period_end = date.fromisoformat(payload["period_end"])
    family_ids = [UUID(value) for value in payload.get("family_ids", [])]
    statement = select(families).where(families.c.organization_id == organization_id)
    if family_ids:
        statement = statement.where(families.c.id.in_(family_ids))
    else:
        statement = statement.where(families.c.status == "active")
    family_rows = list(session.execute(statement.order_by(families.c.name)).mappings())
    items = []
    for family in family_rows:
        guardian = (
            session.execute(
                select(guardians)
                .where(guardians.c.family_id == family["id"])
                .order_by(guardians.c.guardian_type.asc())
            )
            .mappings()
            .first()
        )
        prefill = prefilled_line_items(family["id"], current_user, session, as_of=period_start)
        existing = (
            session.execute(
                select(invoices.c.id, invoices.c.invoice_number, invoices.c.status).where(
                    invoices.c.organization_id == organization_id,
                    invoices.c.family_id == family["id"],
                    invoices.c.period_start == period_start,
                    invoices.c.period_end == period_end,
                    invoices.c.status.notin_({"cancelled", "void"}),
                )
            )
            .mappings()
            .first()
        )
        warnings = []
        if not guardian:
            warnings.append("No guardian is configured")
        elif not guardian["email"]:
            warnings.append("Guardian has no email address")
        missing_rates = [
            child["child_name"] for child in prefill["children"] if child["full_rate"] <= 0
        ]
        if missing_rates:
            warnings.append(f"Missing rate for: {', '.join(missing_rates)}")
        if not prefill["children"]:
            warnings.append("No active children")
        if existing:
            warnings.append(f"Already billed as {existing['invoice_number']}")
        items.append(
            {
                **prefill,
                "guardian_name": (
                    f"{guardian['first_name']} {guardian['last_name']}" if guardian else None
                ),
                "guardian_email": guardian["email"] if guardian else None,
                "existing_invoice": dict(existing) if existing else None,
                "warnings": warnings,
                "ready": bool(prefill["children"] and not missing_rates and not existing),
            }
        )
    return {
        "items": items,
        "summary": {
            "families": len(items),
            "ready": sum(1 for item in items if item["ready"]),
            "needs_attention": sum(1 for item in items if item["warnings"]),
            "existing": sum(1 for item in items if item["existing_invoice"]),
            "total_full_rate": sum((item["total_full_rate"] for item in items), ZERO),
            "total_subsidy": sum((item["total_subsidy"] for item in items), ZERO),
            "total_parent_portion": sum(
                (item["total_parent_portion"] for item in items if item["ready"]), ZERO
            ),
        },
    }


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    _validate_invoice_dates(payload)
    invoice_id = uuid4()
    totals = _invoice_totals(payload)
    values = _invoice_payload_values(payload)
    values.update(
        id=invoice_id,
        organization_id=_organization_id(current_user),
        invoice_number=_next_invoice_number(current_user, session),
        amount_paid=ZERO,
        **totals,
    )
    session.execute(insert(tables["invoices"]).values(**values))
    _replace_line_items(invoice_id, payload, session)
    session.commit()
    return get_invoice(invoice_id, current_user, session)


@router.post("/invoices/bulk-generate", status_code=status.HTTP_201_CREATED)
def bulk_generate_invoices(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    _validate_invoice_dates(payload)
    if not payload.get("period_start") or not payload.get("period_end"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Billing period start and end are required",
        )
    families = tables["families"]
    guardians = tables["guardians"]
    invoices = tables["invoices"]
    generated = []
    errors = []
    skipped = []
    period_start = date.fromisoformat(payload["period_start"])
    period_end = date.fromisoformat(payload["period_end"])
    for raw_family_id in payload.get("family_ids", []):
        try:
            family_id = UUID(raw_family_id)
            family = (
                session.execute(
                    select(families).where(
                        families.c.id == family_id,
                        families.c.organization_id == _organization_id(current_user),
                    )
                )
                .mappings()
                .first()
            )
            if family is None:
                raise ValueError("Family not found")
            existing = (
                session.execute(
                    select(invoices.c.id, invoices.c.invoice_number).where(
                        invoices.c.organization_id == _organization_id(current_user),
                        invoices.c.family_id == family_id,
                        invoices.c.period_start == period_start,
                        invoices.c.period_end == period_end,
                        invoices.c.status.notin_({"cancelled", "void"}),
                    )
                )
                .mappings()
                .first()
            )
            if existing and payload.get("skip_existing", True):
                skipped.append(
                    {
                        "family_id": raw_family_id,
                        "family_name": family["name"],
                        "invoice_id": existing["id"],
                        "invoice_number": existing["invoice_number"],
                        "reason": "already_billed",
                    }
                )
                continue
            guardian = (
                session.execute(
                    select(guardians)
                    .where(guardians.c.family_id == family_id)
                    .order_by(guardians.c.guardian_type.asc())
                )
                .mappings()
                .first()
            )
            prefilled = prefilled_line_items(family_id, current_user, session, as_of=period_start)
            line_items = [
                {
                    "item_type": "daycare_subsidy",
                    "description": f"{child['child_name']} — Childcare",
                    "child_id": child["child_id"],
                    "child_name": child["child_name"],
                    "full_rate": child["full_rate"],
                    "subsidy_amount": child["subsidy"],
                    "amount": child["parent_portion"],
                }
                for child in prefilled["children"]
                if child["full_rate"] > 0
            ]
            if not line_items:
                raise ValueError("No billable children with configured rates")
            address = ""
            if guardian and guardian["address"]:
                address = ", ".join(
                    value
                    for value in [guardian["address"], guardian["city"], guardian["postal_code"]]
                    if value
                )
            result = create_invoice(
                request,
                current_user,
                session,
                {
                    "family_id": raw_family_id,
                    "guardian_id": str(guardian["id"]) if guardian else None,
                    "client_name": (
                        f"{guardian['first_name']} {guardian['last_name']}"
                        if guardian
                        else family["name"]
                    ),
                    "client_email": guardian["email"] if guardian else None,
                    "client_address": address,
                    "recipient_id": payload.get("recipient_id"),
                    "issue_date": payload["issue_date"],
                    "due_date": payload["due_date"],
                    "period_start": payload.get("period_start"),
                    "period_end": payload.get("period_end"),
                    "status": "draft",
                    "line_items": line_items,
                },
            )
            generated.append(result)
        except Exception as exc:
            errors.append(f"{raw_family_id}: {exc}")
    return {
        "items": generated,
        "generated": len(generated),
        "skipped": skipped,
        "errors": errors,
    }


@router.patch("/invoices/bulk-status")
def bulk_update_invoice_status(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    invoice_ids = [UUID(value) for value in payload.get("invoice_ids", [])]
    if invoice_ids:
        session.execute(
            update(tables["invoices"])
            .where(
                tables["invoices"].c.id.in_(invoice_ids),
                tables["invoices"].c.organization_id == _organization_id(current_user),
            )
            .values(status=payload.get("status"))
        )
        session.commit()
    return {"updated": len(invoice_ids)}


@router.post("/invoices/bulk-email")
def bulk_email_invoices(
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    sent = 0
    errors = []
    for raw_invoice_id in payload.get("invoice_ids", []):
        try:
            send_invoice_email(UUID(raw_invoice_id), current_user, session, {})
            sent += 1
        except HTTPException as exc:
            errors.append(f"{raw_invoice_id}: {exc.detail}")
    return {"sent": sent, "errors": errors}


@router.patch("/invoices/{invoice_id}")
def update_invoice(
    invoice_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    current = _get_invoice_row(invoice_id, current_user, session)
    totals = _invoice_totals(payload, current["amount_paid"] or ZERO)
    values = _invoice_payload_values(payload)
    values.update(totals)
    session.execute(
        update(tables["invoices"]).where(tables["invoices"].c.id == invoice_id).values(**values)
    )
    if "line_items" in payload:
        _replace_line_items(invoice_id, payload, session)
    session.commit()
    return get_invoice(invoice_id, current_user, session)


@router.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    return _enrich_invoices([_get_invoice_row(invoice_id, current_user, session)], session)[0]


@router.patch("/invoices/{invoice_id}/status")
def update_invoice_status(
    invoice_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    _ensure_writable(request)
    invoice_status = payload.get("status")
    if invoice_status not in {
        "draft",
        "sent",
        "viewed",
        "partial",
        "paid",
        "overdue",
        "void",
        "cancelled",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid invoice status",
        )
    row = _get_invoice_row(invoice_id, current_user, session)
    invoices = tables["invoices"]
    session.execute(
        update(invoices).where(invoices.c.id == row["id"]).values(status=invoice_status)
    )
    session.commit()
    return {"id": invoice_id, "status": invoice_status}


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> None:
    _ensure_writable(request)
    row = _get_invoice_row(invoice_id, current_user, session)
    session.execute(delete(tables["invoices"]).where(tables["invoices"].c.id == row["id"]))
    session.commit()


@router.post("/invoices/{invoice_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_invoice(
    invoice_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    _ensure_writable(request)
    source = _get_invoice_row(invoice_id, current_user, session)
    invoices = tables["invoices"]
    line_items = tables["invoice_line_items"]
    provider_settings = tables["provider_settings"]
    settings_row = (
        session.execute(
            select(provider_settings).where(
                provider_settings.c.organization_id == _organization_id(current_user)
            )
        )
        .mappings()
        .first()
    )
    if settings_row:
        next_number = settings_row["next_invoice_number"]
        invoice_number = f"{settings_row['invoice_prefix']}-{next_number:05d}"
        session.execute(
            update(provider_settings)
            .where(provider_settings.c.id == settings_row["id"])
            .values(next_invoice_number=next_number + 1)
        )
    else:
        invoice_number = f"DUP-{date.today():%Y%m%d}-{str(uuid4())[:8]}"

    new_id = uuid4()
    excluded = {"id", "invoice_number", "created_at", "updated_at"}
    values = {
        column.name: source[column.name] for column in invoices.c if column.name not in excluded
    }
    values.update(
        id=new_id,
        invoice_number=invoice_number,
        status="draft",
        amount_paid=ZERO,
        balance_due=source["total_amount"],
    )
    session.execute(insert(invoices).values(**values))
    source_items = session.execute(
        select(line_items).where(line_items.c.invoice_id == invoice_id)
    ).mappings()
    for source_item in source_items:
        item_values = {
            column.name: source_item[column.name]
            for column in line_items.c
            if column.name not in {"id", "invoice_id", "created_at"}
        }
        session.execute(insert(line_items).values(id=uuid4(), invoice_id=new_id, **item_values))
    session.commit()
    return {"id": new_id, "invoice_number": invoice_number}


@router.post("/invoices/{invoice_id}/email")
def send_invoice_email(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    invoice = _get_invoice_row(invoice_id, current_user, session)
    provider_settings = tables["provider_settings"]
    settings_row = (
        session.execute(
            select(provider_settings).where(
                provider_settings.c.organization_id == _organization_id(current_user)
            )
        )
        .mappings()
        .first()
    )
    if not settings_row or not settings_row["smtp_enabled"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SMTP is not configured or enabled",
        )
    recipient = invoice["client_email"]
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invoice does not have a recipient email",
        )

    message = EmailMessage()
    message["Subject"] = f"Invoice {invoice['invoice_number']}"
    message["From"] = settings_row["smtp_from_email"]
    message["To"] = recipient
    custom_message = payload.get("custom_message") or "Please find your invoice summary below."
    message.set_content(
        f"{custom_message}\n\n"
        f"Invoice: {invoice['invoice_number']}\n"
        f"Issue date: {invoice['issue_date']}\n"
        f"Due date: {invoice['due_date']}\n"
        f"Total: {settings_row['currency_symbol']}{invoice['total_amount']}\n"
        f"Balance due: {settings_row['currency_symbol']}{invoice['balance_due']}\n"
    )
    host = settings_row["smtp_host"]
    port = settings_row["smtp_port"]
    if not host or not port or not settings_row["smtp_from_email"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SMTP settings are incomplete",
        )
    try:
        if settings_row["smtp_encryption"] == "ssl":
            smtp = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            smtp = smtplib.SMTP(host, port, timeout=20)
            if settings_row["smtp_encryption"] in {"tls", "starttls"}:
                smtp.starttls()
        with smtp:
            if settings_row["smtp_username"]:
                smtp.login(settings_row["smtp_username"], settings_row["smtp_password"] or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMTP delivery failed: {error}",
        ) from error
    return {"success": True, "message": "Invoice email sent"}


@router.post("/recurring/{schedule_id}/generate", status_code=status.HTTP_201_CREATED)
def generate_recurring_invoice(
    schedule_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    _ensure_writable(request)
    organization_id = _organization_id(current_user)
    recurring = tables["recurring_invoices"]
    row = (
        session.execute(
            select(recurring).where(
                recurring.c.id == schedule_id,
                recurring.c.organization_id == organization_id,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurring schedule not found"
        )
    raw_items = row["line_items"] or "[]"
    try:
        items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
    except json.JSONDecodeError:
        items = []
    subtotal = sum((Decimal(str(item.get("amount", 0))) for item in items), ZERO)
    tax_rate = row["tax_rate"] or ZERO
    tax_amount = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
    discount = row["discount_amount"] or ZERO
    total = max(ZERO, subtotal + tax_amount - discount)
    provider_settings = tables["provider_settings"]
    settings_row = (
        session.execute(
            select(provider_settings).where(provider_settings.c.organization_id == organization_id)
        )
        .mappings()
        .first()
    )
    if settings_row:
        next_number = settings_row["next_invoice_number"]
        invoice_number = f"{settings_row['invoice_prefix']}{next_number:04d}"
        session.execute(
            update(provider_settings)
            .where(provider_settings.c.id == settings_row["id"])
            .values(next_invoice_number=next_number + 1)
        )
    else:
        invoice_number = f"INV-{date.today():%Y%m%d}-{str(uuid4())[:8]}"
    invoice_id = uuid4()
    issue_date = date.today()
    session.execute(
        insert(tables["invoices"]).values(
            id=invoice_id,
            organization_id=organization_id,
            invoice_number=invoice_number,
            issue_date=issue_date,
            due_date=issue_date + timedelta(days=row["due_days"]),
            subtotal=subtotal,
            discount_amount=discount,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            total_amount=total,
            amount_paid=ZERO,
            balance_due=total,
            status="draft",
            family_id=row["family_id"],
            guardian_id=row["guardian_id"],
            client_name=row["client_name"],
            client_email=row["client_email"],
            client_address=row["client_address"],
            notes=row["notes"],
            terms=row["terms"],
        )
    )
    for item in items:
        session.execute(
            insert(tables["invoice_line_items"]).values(
                id=uuid4(),
                invoice_id=invoice_id,
                item_type=item.get("item_type", "service_flat"),
                description=item.get("description") or "Recurring service",
                quantity=Decimal("1"),
                amount=Decimal(str(item.get("amount", 0))),
            )
        )
    next_date = _advance_recurring_date(issue_date, row["frequency"])
    session.execute(
        update(recurring)
        .where(recurring.c.id == schedule_id)
        .values(
            invoices_generated=row["invoices_generated"] + 1,
            last_invoice_date=issue_date,
            next_invoice_date=next_date,
        )
    )
    session.commit()
    return {"id": invoice_id, "invoice_number": invoice_number}
