"""Organization-scoped read access to legacy CareSync resources."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from sqlalchemy import String, Text, and_, cast, delete, exists, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import Select

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Base

router = APIRouter(prefix="/resources", tags=["resources"])
TABLES = Base.metadata.tables
HIDDEN_COLUMNS: dict[str, set[str]] = {
    "users": {"password"},
    "provider_settings": {"smtp_password"},
    "child_ai_messages": {"image_base64"},
    "signatures": {"image_data"},
}
RESERVED_PARAMETERS = {"limit", "offset", "search", "sort", "order"}
WRITE_PROTECTED_RESOURCES = {
    "activity_logs",
    "organization_members",
    "organizations",
    "permissions",
    "role_permissions",
    "roles",
    "users",
}


def _organization_condition(table_name: str, organization_id: UUID):
    table = TABLES[table_name]
    if table_name == "organizations":
        return table.c.id == organization_id
    if "organization_id" in table.c:
        return table.c.organization_id == organization_id

    families = TABLES["families"]
    children = TABLES["children"]
    invoices = TABLES["invoices"]
    users = TABLES["users"]
    if table_name in {"guardians", "emergency_contacts"}:
        return exists(
            select(1).where(
                families.c.id == table.c.family_id,
                families.c.organization_id == organization_id,
            )
        )
    if table_name == "child_funding":
        return exists(
            select(1)
            .select_from(children.join(families, children.c.family_id == families.c.id))
            .where(
                func.replace(cast(children.c.id, String), "-", "")
                == func.replace(cast(table.c.child_id, String), "-", ""),
                families.c.organization_id == organization_id,
            )
        )
    if table_name == "scheduled_attendance":
        imported_claims = TABLES["imported_claims"]
        real_child = exists(
            select(1)
            .select_from(children.join(families, children.c.family_id == families.c.id))
            .where(
                cast(children.c.id, String) == cast(table.c.child_id, String),
                families.c.organization_id == organization_id,
            )
        )
        imported_child = exists(
            select(1).where(
                imported_claims.c.organization_id == organization_id,
                imported_claims.c.import_batch_id == table.c.source_claim_batch_id,
                func.replace(cast(imported_claims.c.id, String), "-", "")
                == func.replace(
                    func.replace(cast(table.c.child_id, String), "imported-claim:", ""),
                    "-",
                    "",
                ),
                table.c.child_id.startswith("imported-claim:"),
            )
        )
        return or_(real_child, imported_child)
    if table_name in {"invoice_line_items", "invoice_allocations", "payments"}:
        return exists(
            select(1).where(
                invoices.c.id == table.c.invoice_id,
                invoices.c.organization_id == organization_id,
            )
        )
    if table_name == "generated_claims":
        reports = TABLES["generated_claim_reports"]
        return exists(
            select(1).where(
                reports.c.id == table.c.report_id,
                reports.c.organization_id == organization_id,
            )
        )
    if table_name == "credit_applications":
        notes = TABLES["credit_notes"]
        return exists(
            select(1).where(
                notes.c.id == table.c.credit_note_id,
                notes.c.organization_id == organization_id,
            )
        )
    if table_name == "portfolio_images":
        entries = TABLES["portfolio_entries"]
        return exists(
            select(1).where(
                entries.c.id == table.c.entry_id,
                entries.c.organization_id == organization_id,
            )
        )
    if table_name == "signatures":
        guardians = TABLES["guardians"]
        return exists(
            select(1)
            .select_from(guardians.join(families, guardians.c.family_id == families.c.id))
            .where(
                guardians.c.id == table.c.guardian_id,
                families.c.organization_id == organization_id,
            )
        )
    if table_name in {"staff_profiles", "staff_education"}:
        return exists(
            select(1).where(
                users.c.id == table.c.user_id,
                users.c.organization_id == organization_id,
            )
        )
    return None


def _visible_columns(table_name: str):
    hidden = HIDDEN_COLUMNS.get(table_name, set())
    return [column for column in TABLES[table_name].c if column.name not in hidden]


def _parse_filter(column, raw_value: str) -> Any:
    try:
        value_type = column.type.python_type
    except NotImplementedError:
        return raw_value
    if value_type is bool:
        normalized = raw_value.lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise ValueError("expected a boolean")
        return normalized in {"true", "1"}
    if value_type is UUID:
        return UUID(raw_value)
    if value_type is int:
        return int(raw_value)
    if value_type is float:
        return float(raw_value)
    if value_type is Decimal:
        return Decimal(raw_value)
    if value_type is date:
        return date.fromisoformat(raw_value)
    if value_type is datetime:
        return datetime.fromisoformat(raw_value)
    if value_type in {dict, list}:
        return json.loads(raw_value)
    return raw_value


def _coerce_value(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _parse_filter(column, value)
    return value


def _ensure_writable(request: Request, resource_name: str) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )
    if resource_name in WRITE_PROTECTED_RESOURCES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This resource requires a dedicated workflow",
        )


def _mutation_values(
    table_name: str,
    payload: dict[str, Any],
    current_user: CurrentUser,
    *,
    creating: bool,
) -> dict[str, Any]:
    table = TABLES[table_name]
    hidden = HIDDEN_COLUMNS.get(table_name, set())
    allowed = {
        column.name
        for column in table.c
        if column.name not in hidden
        and column.name not in {"created_at", "updated_at"}
        and (not column.primary_key or not creating)
    }
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown or protected fields: {', '.join(sorted(unknown))}",
        )
    values: dict[str, Any] = {}
    for key, value in payload.items():
        try:
            values[key] = _coerce_value(table.c[key], value)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid value for {key}: {error}",
            ) from None
    if creating and current_user.organization_id and "organization_id" in table.c:
        supplied = values.get("organization_id")
        if supplied is not None and supplied != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create a resource for another organization",
            )
        values["organization_id"] = current_user.organization_id
    return values


def _apply_scope(
    statement: Select, table_name: str, current_user: CurrentUser
) -> Select:
    if current_user.organization_id is None:
        return statement
    condition = _organization_condition(table_name, current_user.organization_id)
    return statement.where(condition) if condition is not None else statement


@router.get("")
def list_resource_types(_current_user: CurrentUser) -> dict[str, list[str]]:
    return {"resources": sorted(TABLES)}


@router.get("/{resource_name}", response_model=None)
def list_resources(
    resource_name: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    sort: str | None = None,
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> list[dict[str, Any]]:
    table = TABLES.get(resource_name)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    columns = _visible_columns(resource_name)
    if resource_name == "scheduled_attendance" and current_user.organization_id:
        imported_claims = TABLES["imported_claims"]
        columns = [
            *columns,
            select(imported_claims.c.child_name)
            .where(
                imported_claims.c.organization_id == current_user.organization_id,
                imported_claims.c.import_batch_id == table.c.source_claim_batch_id,
                func.replace(cast(imported_claims.c.id, String), "-", "")
                == func.replace(
                    func.replace(cast(table.c.child_id, String), "imported-claim:", ""),
                    "-",
                    "",
                ),
            )
            .scalar_subquery()
            .label("child_name"),
        ]
    statement = _apply_scope(select(*columns), resource_name, current_user)
    if search:
        searchable = [
            column
            for column in columns
            if isinstance(column.type, (String, Text))
        ]
        if searchable:
            statement = statement.where(
                or_(*(cast(column, String).ilike(f"%{search}%") for column in searchable))
            )
    filter_conditions = []
    for key, raw_value in request.query_params.multi_items():
        if key in RESERVED_PARAMETERS:
            continue
        column = table.c.get(key)
        if column is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown filter column: {key}",
            )
        try:
            filter_conditions.append(column == _parse_filter(column, raw_value))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid value for {key}: {error}",
            ) from None
    if filter_conditions:
        statement = statement.where(and_(*filter_conditions))
    sort_column = table.c.get(sort) if sort else next(iter(table.primary_key.columns), None)
    if sort and sort_column is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown sort column: {sort}",
        )
    if sort_column is not None:
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc()
        )
    statement = statement.limit(limit).offset(offset)
    return [dict(row) for row in session.execute(statement).mappings()]


@router.get("/{resource_name}/{resource_id}", response_model=None)
def get_resource(
    resource_name: str,
    resource_id: str,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict[str, Any]:
    table = TABLES.get(resource_name)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    primary_keys = list(table.primary_key.columns)
    if len(primary_keys) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Composite-key resources require list filters",
        )
    key = primary_keys[0]
    try:
        parsed_id = _parse_filter(key, resource_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid resource identifier",
        ) from None
    statement = select(*_visible_columns(resource_name)).where(key == parsed_id)
    statement = _apply_scope(statement, resource_name, current_user)
    row = session.execute(statement).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return dict(row)


@router.post("/{resource_name}", response_model=None, status_code=status.HTTP_201_CREATED)
def create_resource(
    resource_name: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    table = TABLES.get(resource_name)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    _ensure_writable(request, resource_name)
    values = _mutation_values(resource_name, payload, current_user, creating=True)
    try:
        row = session.execute(
            insert(table).values(**values).returning(*_visible_columns(resource_name))
        ).mappings().one()
        condition = (
            _organization_condition(resource_name, current_user.organization_id)
            if current_user.organization_id
            else None
        )
        if condition is not None:
            primary_keys = list(table.primary_key.columns)
            identity = and_(*(key == row[key.name] for key in primary_keys))
            scoped = session.execute(
                select(1).select_from(table).where(identity, condition)
            ).first()
            if scoped is None:
                session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Related records belong to another organization",
                )
        session.commit()
        return dict(row)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The resource violates a database constraint",
        ) from error


@router.patch("/{resource_name}/{resource_id}", response_model=None)
def update_resource(
    resource_name: str,
    resource_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    table = TABLES.get(resource_name)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    _ensure_writable(request, resource_name)
    primary_keys = list(table.primary_key.columns)
    if len(primary_keys) != 1:
        raise HTTPException(status_code=400, detail="Composite keys are not mutable here")
    key = primary_keys[0]
    try:
        parsed_id = _parse_filter(key, resource_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid resource identifier") from None
    values = _mutation_values(resource_name, payload, current_user, creating=False)
    values.pop(key.name, None)
    if "updated_at" in table.c:
        values["updated_at"] = datetime.now()
    statement = update(table).where(key == parsed_id)
    statement = _apply_scope(statement, resource_name, current_user)
    try:
        row = session.execute(
            statement.values(**values).returning(*_visible_columns(resource_name))
        ).mappings().first()
        if row is None:
            session.rollback()
            raise HTTPException(status_code=404, detail="Resource not found")
        session.commit()
        return dict(row)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Database constraint violation") from error


@router.delete("/{resource_name}/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_name: str,
    resource_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    confirm: bool = False,
) -> None:
    table = TABLES.get(resource_name)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    _ensure_writable(request, resource_name)
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deletion requires confirm=true",
        )
    primary_keys = list(table.primary_key.columns)
    if len(primary_keys) != 1:
        raise HTTPException(status_code=400, detail="Composite keys are not mutable here")
    key = primary_keys[0]
    try:
        parsed_id = _parse_filter(key, resource_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid resource identifier") from None
    statement = delete(table).where(key == parsed_id)
    statement = _apply_scope(statement, resource_name, current_user)
    try:
        result = session.execute(statement)
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=404, detail="Resource not found")
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Database constraint violation") from error
