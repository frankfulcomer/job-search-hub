from dataclasses import dataclass
from datetime import date, datetime, timezone

WORK_ARRANGEMENTS = ("ONSITE", "HYBRID", "REMOTE")
EMPLOYMENT_TYPES = ("FULL_TIME", "PART_TIME", "CONTRACT", "TEMPORARY")
COMPENSATION_BASES = ("ANNUAL", "HOURLY")
DEFAULT_INITIAL_STATUS = "APPLIED"

# Matches the whitespace convention in schema.sql / ADR 0001: space, tab, CR, LF.
_INSIGNIFICANT_WHITESPACE = " \t\r\n"
_NORMALIZE_SQL = "lower(trim({expr}, char(32) || char(9) || char(13) || char(10)))"


class ValidationError(Exception):
    def __init__(self, field, message):
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass
class LocationInput:
    city: str | None = None
    state_province: str | None = None
    country: str | None = None


@dataclass
class CreateApplicationResult:
    application_id: int
    company_id: int
    source_id: int
    job_location_id: int | None
    initial_status_id: int
    status_history_id: int


def _trim(value):
    if value is None:
        return None
    return value.strip(_INSIGNIFICANT_WHITESPACE)


def _require_text(field, value):
    trimmed = _trim(value)
    if not trimmed:
        raise ValidationError(field, "is required")
    return trimmed


def _require_enum(field, value, allowed):
    if value is not None and value not in allowed:
        raise ValidationError(field, f"must be one of {sorted(allowed)}")
    return value


def _format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def _resolve_or_create_company(connection, name, hq_location: LocationInput | None):
    row = connection.execute(
        f"SELECT company_id FROM company WHERE {_NORMALIZE_SQL.format(expr='name')} = "
        f"{_NORMALIZE_SQL.format(expr='?')}",
        (name,),
    ).fetchone()
    if row is not None:
        return row["company_id"]

    # Only resolve/create a headquarters location when the company itself is
    # new; an existing company keeps its own headquarters (architecture.md).
    hq_location_id = _resolve_or_create_location(connection, hq_location)
    cursor = connection.execute(
        "INSERT INTO company (name, hq_location_id) VALUES (?, ?)",
        (name, hq_location_id),
    )
    return cursor.lastrowid


def _resolve_or_create_source(connection, name):
    row = connection.execute(
        f"SELECT source_id FROM source WHERE {_NORMALIZE_SQL.format(expr='name')} = "
        f"{_NORMALIZE_SQL.format(expr='?')}",
        (name,),
    ).fetchone()
    if row is not None:
        return row["source_id"]

    cursor = connection.execute("INSERT INTO source (name) VALUES (?)", (name,))
    return cursor.lastrowid


def _resolve_or_create_location(connection, location: LocationInput | None):
    if location is None:
        return None

    city = _trim(location.city) or None
    state_province = _trim(location.state_province) or None
    country = _trim(location.country) or None

    if city is None and state_province is None and country is None:
        return None

    component_expr = _NORMALIZE_SQL.format(expr="coalesce({0}, '')")
    row = connection.execute(
        f"SELECT location_id FROM location WHERE "
        f"{component_expr.format('city')} = {component_expr.format('?')} AND "
        f"{component_expr.format('state_province')} = {component_expr.format('?')} AND "
        f"{component_expr.format('country')} = {component_expr.format('?')}",
        (city, state_province, country),
    ).fetchone()
    if row is not None:
        return row["location_id"]

    cursor = connection.execute(
        "INSERT INTO location (city, state_province, country) VALUES (?, ?, ?)",
        (city, state_province, country),
    )
    return cursor.lastrowid


def _resolve_status_id(connection, status_name):
    row = connection.execute(
        "SELECT status_id FROM status WHERE name = ?", (status_name,)
    ).fetchone()
    if row is None:
        raise ValidationError("initial_status_name", f"unknown status {status_name!r}")
    return row["status_id"]


def _resolve_initial_effective_at(
    status_name, application_date, initial_status_effective_at, now
):
    if initial_status_effective_at is not None:
        effective_at = initial_status_effective_at
    elif status_name == DEFAULT_INITIAL_STATUS and application_date == now.date():
        effective_at = now
    else:
        raise ValidationError(
            "initial_status_effective_at",
            "is required unless the initial status is APPLIED and the "
            "application date is today",
        )

    if effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=timezone.utc)
    if effective_at.astimezone(timezone.utc) > now:
        raise ValidationError(
            "initial_status_effective_at", "must not be in the future"
        )

    return effective_at


def create_application(
    connection,
    *,
    company_name,
    job_title,
    application_date: date,
    source_name,
    initial_status_name=DEFAULT_INITIAL_STATUS,
    initial_status_effective_at: datetime | None = None,
    job_location: LocationInput | None = None,
    company_hq_location: LocationInput | None = None,
    job_description=None,
    job_url=None,
    external_job_id=None,
    work_arrangement=None,
    employment_type=None,
    compensation_min=None,
    compensation_max=None,
    compensation_basis=None,
    notes=None,
    now: datetime | None = None,
) -> CreateApplicationResult:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    company_name = _require_text("company_name", company_name)
    job_title = _require_text("job_title", job_title)
    source_name = _require_text("source_name", source_name)
    if application_date is None:
        raise ValidationError("application_date", "is required")

    work_arrangement = _require_enum(
        "work_arrangement", work_arrangement, WORK_ARRANGEMENTS
    )
    employment_type = _require_enum(
        "employment_type", employment_type, EMPLOYMENT_TYPES
    )
    compensation_basis = _require_enum(
        "compensation_basis", compensation_basis, COMPENSATION_BASES
    )

    external_job_id = _trim(external_job_id) or None
    job_url = _trim(job_url) or None

    try:
        status_id = _resolve_status_id(connection, initial_status_name)
        effective_at = _resolve_initial_effective_at(
            initial_status_name, application_date, initial_status_effective_at, now
        )

        company_id = _resolve_or_create_company(
            connection, company_name, company_hq_location
        )
        source_id = _resolve_or_create_source(connection, source_name)
        job_location_id = _resolve_or_create_location(connection, job_location)

        cursor = connection.execute(
            """
            INSERT INTO application (
                company_id, job_location_id, source_id, job_title,
                external_job_id, job_url, job_description, work_arrangement,
                employment_type, compensation_min, compensation_max,
                compensation_basis, application_date, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                job_location_id,
                source_id,
                job_title,
                external_job_id,
                job_url,
                job_description,
                work_arrangement,
                employment_type,
                compensation_min,
                compensation_max,
                compensation_basis,
                _format_date(application_date),
                notes,
            ),
        )
        application_id = cursor.lastrowid

        history_cursor = connection.execute(
            """
            INSERT INTO application_status_history (
                application_id, status_id, effective_at
            ) VALUES (?, ?, ?)
            """,
            (application_id, status_id, _format_timestamp(effective_at)),
        )
        status_history_id = history_cursor.lastrowid

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return CreateApplicationResult(
        application_id=application_id,
        company_id=company_id,
        source_id=source_id,
        job_location_id=job_location_id,
        initial_status_id=status_id,
        status_history_id=status_history_id,
    )


# Maps the seven FR-003 list columns to their SQL sort expression(s).
# FR-003 doesn't define sort keys for compound/reference columns; confirmed
# 2026-09-20 (see docs/journal/2026-09.md): "status" sorts alphabetically by
# the displayed status name (not STATUS.display_order's lifecycle sequence),
# and "job_location" sorts by its displayed components, city then
# state/province then country.
LIST_SORT_COLUMNS = {
    "company": ("c.name",),
    "job_title": ("a.job_title",),
    "job_location": ("l.city", "l.state_province", "l.country"),
    "work_arrangement": ("a.work_arrangement",),
    "application_date": ("a.application_date",),
    "status": ("st.name",),
    "source": ("s.name",),
}
LIST_DEFAULT_SORT = "application_date"
LIST_DEFAULT_DIRECTION = "desc"
LIST_PAGE_SIZE = 25


@dataclass
class ApplicationListItem:
    application_id: int
    company_name: str
    job_title: str
    job_location_city: str | None
    job_location_state_province: str | None
    job_location_country: str | None
    work_arrangement: str | None
    application_date: str
    source_name: str
    status_name: str

    @property
    def job_location_display(self):
        parts = [
            self.job_location_city,
            self.job_location_state_province,
            self.job_location_country,
        ]
        return ", ".join(part for part in parts if part) or None


@dataclass
class ApplicationListPage:
    items: list[ApplicationListItem]
    sort: str
    direction: str
    page: int
    page_size: int
    total_count: int

    @property
    def total_pages(self):
        if self.total_count == 0:
            return 1
        return -(-self.total_count // self.page_size)


_LIST_QUERY = """
    WITH current_status AS (
        SELECT application_id, status_id
        FROM (
            SELECT application_id, status_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY application_id ORDER BY effective_at DESC
                   ) AS rn
            FROM application_status_history
        )
        WHERE rn = 1
    )
    SELECT
        a.application_id,
        c.name AS company_name,
        a.job_title,
        l.city AS job_location_city,
        l.state_province AS job_location_state_province,
        l.country AS job_location_country,
        a.work_arrangement,
        a.application_date,
        s.name AS source_name,
        st.name AS status_name
    FROM application a
    JOIN company c ON c.company_id = a.company_id
    JOIN source s ON s.source_id = a.source_id
    LEFT JOIN location l ON l.location_id = a.job_location_id
    JOIN current_status cs ON cs.application_id = a.application_id
    JOIN status st ON st.status_id = cs.status_id
    WHERE a.archived_at IS NULL
    ORDER BY {order_by}
    LIMIT ? OFFSET ?
"""


def list_applications(
    connection,
    *,
    sort=LIST_DEFAULT_SORT,
    direction=LIST_DEFAULT_DIRECTION,
    page=1,
) -> ApplicationListPage:
    if sort not in LIST_SORT_COLUMNS:
        sort = LIST_DEFAULT_SORT
    if direction not in ("asc", "desc"):
        direction = LIST_DEFAULT_DIRECTION
    if not isinstance(page, int) or page < 1:
        page = 1

    total_count = connection.execute(
        "SELECT COUNT(*) AS n FROM application WHERE archived_at IS NULL"
    ).fetchone()["n"]

    page_size = LIST_PAGE_SIZE
    total_pages = max(1, -(-total_count // page_size))
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * page_size

    sql_direction = "ASC" if direction == "asc" else "DESC"
    order_terms = [f"{column} {sql_direction}" for column in LIST_SORT_COLUMNS[sort]]
    order_terms.append(f"a.application_id {sql_direction}")
    order_by = ", ".join(order_terms)

    rows = connection.execute(
        _LIST_QUERY.format(order_by=order_by), (page_size, offset)
    ).fetchall()

    items = [
        ApplicationListItem(
            application_id=row["application_id"],
            company_name=row["company_name"],
            job_title=row["job_title"],
            job_location_city=row["job_location_city"],
            job_location_state_province=row["job_location_state_province"],
            job_location_country=row["job_location_country"],
            work_arrangement=row["work_arrangement"],
            application_date=row["application_date"],
            source_name=row["source_name"],
            status_name=row["status_name"],
        )
        for row in rows
    ]

    return ApplicationListPage(
        items=items,
        sort=sort,
        direction=direction,
        page=page,
        page_size=page_size,
        total_count=total_count,
    )
