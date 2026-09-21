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


def _resolve_or_create_company(connection, name, hq_location: LocationInput | None = None):
    """Find or create a company by normalized name.

    Returns (company_id, was_created). An existing company's headquarters is
    never touched here (architecture.md); hq_location is only used to seed a
    newly-created company's headquarters, matching create_application's
    "new company, optional headquarters" behavior.
    """
    row = connection.execute(
        f"SELECT company_id FROM company WHERE {_NORMALIZE_SQL.format(expr='name')} = "
        f"{_NORMALIZE_SQL.format(expr='?')}",
        (name,),
    ).fetchone()
    if row is not None:
        return row["company_id"], False

    hq_location_id = _resolve_or_create_location(connection, hq_location)
    cursor = connection.execute(
        "INSERT INTO company (name, hq_location_id) VALUES (?, ?)",
        (name, hq_location_id),
    )
    return cursor.lastrowid, True


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


def _resolve_status_id(connection, status_name, field="initial_status_name"):
    row = connection.execute(
        "SELECT status_id FROM status WHERE name = ?", (status_name,)
    ).fetchone()
    if row is None:
        raise ValidationError(field, f"unknown status {status_name!r}")
    return row["status_id"]


def _reject_future_effective_at(field, effective_at, now):
    if effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=timezone.utc)
    if effective_at.astimezone(timezone.utc) > now:
        raise ValidationError(field, "must not be in the future")
    return effective_at


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

    return _reject_future_effective_at(
        "initial_status_effective_at", effective_at, now
    )


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
    # Defaults to local time, not UTC: _resolve_initial_effective_at compares
    # application_date (a local-calendar-meaning date, e.g. from the create
    # form's date.today() default) against now.date(). A UTC-aware default
    # disagrees with local "today" for several hours daily in any negative
    # UTC-offset timezone. _format_timestamp still normalizes to UTC before
    # storage regardless of now's tzinfo, so persisted values are unaffected.
    now = now or datetime.now().astimezone()
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

        company_id, _ = _resolve_or_create_company(
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


def _format_location(city, state_province, country):
    parts = [city, state_province, country]
    return ", ".join(part for part in parts if part) or None


def _format_number(value):
    if value is None:
        return None
    if value == int(value):
        return str(int(value))
    return str(value)


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
    archived_at: str | None

    @property
    def job_location_display(self):
        return _format_location(
            self.job_location_city,
            self.job_location_state_province,
            self.job_location_country,
        )

    @property
    def is_archived(self):
        return self.archived_at is not None


@dataclass
class ApplicationListPage:
    items: list[ApplicationListItem]
    sort: str
    direction: str
    page: int
    page_size: int
    total_count: int
    record_state: str

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
        st.name AS status_name,
        a.archived_at
    FROM application a
    JOIN company c ON c.company_id = a.company_id
    JOIN source s ON s.source_id = a.source_id
    LEFT JOIN location l ON l.location_id = a.job_location_id
    JOIN current_status cs ON cs.application_id = a.application_id
    JOIN status st ON st.status_id = cs.status_id
    WHERE {record_state_where}
    ORDER BY {order_by}
    LIMIT ? OFFSET ?
"""

# Minimal FR-009 record-state visibility (Active/Archived/All), scoped ahead
# of FR-004's full search/filter feature. Deliberately reuses the same list
# query, sort, and pagination path per architecture.md's "Archived and All
# record-state filters expose historical applications using the same search,
# filter, sort, and pagination behavior" so FR-004 can extend this later
# rather than replace it.
RECORD_STATES = {
    "active": "a.archived_at IS NULL",
    "archived": "a.archived_at IS NOT NULL",
    "all": "1 = 1",
}
LIST_DEFAULT_RECORD_STATE = "active"


def list_applications(
    connection,
    *,
    sort=LIST_DEFAULT_SORT,
    direction=LIST_DEFAULT_DIRECTION,
    page=1,
    record_state=LIST_DEFAULT_RECORD_STATE,
) -> ApplicationListPage:
    if sort not in LIST_SORT_COLUMNS:
        sort = LIST_DEFAULT_SORT
    if direction not in ("asc", "desc"):
        direction = LIST_DEFAULT_DIRECTION
    if not isinstance(page, int) or page < 1:
        page = 1
    if record_state not in RECORD_STATES:
        record_state = LIST_DEFAULT_RECORD_STATE

    record_state_where = RECORD_STATES[record_state]

    total_count = connection.execute(
        f"SELECT COUNT(*) AS n FROM application a WHERE {record_state_where}"
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
        _LIST_QUERY.format(record_state_where=record_state_where, order_by=order_by),
        (page_size, offset),
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
            archived_at=row["archived_at"],
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
        record_state=record_state,
    )


@dataclass
class StatusHistoryEntry:
    application_status_history_id: int
    status_name: str
    effective_at: str
    notes: str | None
    is_current: bool


@dataclass
class ApplicationDetail:
    application_id: int
    company_name: str
    job_title: str
    application_date: str
    source_name: str
    work_arrangement: str | None
    employment_type: str | None
    compensation_min: float | None
    compensation_max: float | None
    compensation_basis: str | None
    external_job_id: str | None
    job_url: str | None
    job_description: str | None
    notes: str | None
    job_location_city: str | None
    job_location_state_province: str | None
    job_location_country: str | None
    company_hq_city: str | None
    company_hq_state_province: str | None
    company_hq_country: str | None
    archived_at: str | None
    status_history: list[StatusHistoryEntry]

    @property
    def is_archived(self):
        return self.archived_at is not None

    @property
    def job_location_display(self):
        return _format_location(
            self.job_location_city,
            self.job_location_state_province,
            self.job_location_country,
        )

    @property
    def company_hq_display(self):
        return _format_location(
            self.company_hq_city,
            self.company_hq_state_province,
            self.company_hq_country,
        )

    @property
    def current_status_name(self):
        return self.status_history[-1].status_name if self.status_history else None

    @property
    def compensation_min_display(self):
        return _format_number(self.compensation_min)

    @property
    def compensation_max_display(self):
        return _format_number(self.compensation_max)

    @property
    def job_url_is_safe_link(self):
        # job_url has no format validation on entry (FR-011 URL validation is
        # intentionally deferred; see the Create Application slice). Only
        # render it as a clickable href for http(s) schemes, so a stored
        # value like "javascript:..." displays as inert text instead of an
        # executable link.
        if not self.job_url:
            return False
        return self.job_url.strip().lower().startswith(("http://", "https://"))


_DETAIL_QUERY = """
    SELECT
        a.application_id,
        a.job_title,
        a.application_date,
        a.work_arrangement,
        a.employment_type,
        a.compensation_min,
        a.compensation_max,
        a.compensation_basis,
        a.external_job_id,
        a.job_url,
        a.job_description,
        a.notes,
        c.name AS company_name,
        s.name AS source_name,
        jl.city AS job_location_city,
        jl.state_province AS job_location_state_province,
        jl.country AS job_location_country,
        hql.city AS company_hq_city,
        hql.state_province AS company_hq_state_province,
        hql.country AS company_hq_country,
        a.archived_at
    FROM application a
    JOIN company c ON c.company_id = a.company_id
    JOIN source s ON s.source_id = a.source_id
    LEFT JOIN location jl ON jl.location_id = a.job_location_id
    LEFT JOIN location hql ON hql.location_id = c.hq_location_id
    WHERE a.application_id = ?
"""

_DETAIL_HISTORY_QUERY = """
    SELECT
        ash.application_status_history_id,
        ash.effective_at,
        ash.notes,
        st.name AS status_name
    FROM application_status_history ash
    JOIN status st ON st.status_id = ash.status_id
    WHERE ash.application_id = ?
    ORDER BY ash.effective_at ASC
"""


def get_application_detail(connection, application_id) -> ApplicationDetail | None:
    row = connection.execute(_DETAIL_QUERY, (application_id,)).fetchone()
    if row is None:
        return None

    history_rows = connection.execute(
        _DETAIL_HISTORY_QUERY, (application_id,)
    ).fetchall()
    # UNIQUE(application_id, effective_at) guarantees no tie for "latest";
    # ascending order (required display order) puts it last.
    history = [
        StatusHistoryEntry(
            application_status_history_id=r["application_status_history_id"],
            status_name=r["status_name"],
            effective_at=r["effective_at"],
            notes=r["notes"],
            is_current=(i == len(history_rows) - 1),
        )
        for i, r in enumerate(history_rows)
    ]

    return ApplicationDetail(
        application_id=row["application_id"],
        job_title=row["job_title"],
        application_date=row["application_date"],
        company_name=row["company_name"],
        source_name=row["source_name"],
        work_arrangement=row["work_arrangement"],
        employment_type=row["employment_type"],
        compensation_min=row["compensation_min"],
        compensation_max=row["compensation_max"],
        compensation_basis=row["compensation_basis"],
        external_job_id=row["external_job_id"],
        job_url=row["job_url"],
        job_description=row["job_description"],
        notes=row["notes"],
        job_location_city=row["job_location_city"],
        job_location_state_province=row["job_location_state_province"],
        job_location_country=row["job_location_country"],
        company_hq_city=row["company_hq_city"],
        company_hq_state_province=row["company_hq_state_province"],
        company_hq_country=row["company_hq_country"],
        archived_at=row["archived_at"],
        status_history=history,
    )


class SharedHeadquartersChangeRequiresConfirmation(Exception):
    """Raised when an edit would change a company's headquarters and that
    company is associated with other applications (FR-006). Nothing is
    persisted when this is raised; the caller must resubmit with
    confirm_shared_headquarters_change=True to apply the change."""

    def __init__(
        self,
        company_name,
        affected_application_count,
        current_headquarters_display,
        new_headquarters_display,
    ):
        super().__init__(
            f"Changing the headquarters for {company_name!r} affects "
            f"{affected_application_count} other application(s)"
        )
        self.company_name = company_name
        self.affected_application_count = affected_application_count
        self.current_headquarters_display = current_headquarters_display
        self.new_headquarters_display = new_headquarters_display


@dataclass
class EditApplicationResult:
    application_id: int
    company_id: int
    source_id: int
    job_location_id: int | None
    company_reassigned: bool


def _location_id_display(connection, location_id):
    if location_id is None:
        return None
    row = connection.execute(
        "SELECT city, state_province, country FROM location WHERE location_id = ?",
        (location_id,),
    ).fetchone()
    if row is None:
        return None
    return _format_location(row["city"], row["state_province"], row["country"])


def _apply_company_headquarters_change(
    connection, company_id, is_new_company, hq_location, application_id, confirmed
):
    new_city = _trim(hq_location.city) if hq_location else None
    new_state_province = _trim(hq_location.state_province) if hq_location else None
    new_country = _trim(hq_location.country) if hq_location else None

    current_hq_id = connection.execute(
        "SELECT hq_location_id FROM company WHERE company_id = ?", (company_id,)
    ).fetchone()["hq_location_id"]
    new_hq_id = _resolve_or_create_location(connection, hq_location)

    if new_hq_id == current_hq_id:
        return

    if not is_new_company:
        # A brand-new company (created earlier in this same edit) can't yet
        # be associated with any other application, so its headquarters can
        # be set directly regardless of confirmation.
        other_application_count = connection.execute(
            "SELECT COUNT(*) AS n FROM application "
            "WHERE company_id = ? AND application_id != ?",
            (company_id, application_id),
        ).fetchone()["n"]
        if other_application_count > 0 and not confirmed:
            company_name = connection.execute(
                "SELECT name FROM company WHERE company_id = ?", (company_id,)
            ).fetchone()["name"]
            raise SharedHeadquartersChangeRequiresConfirmation(
                company_name=company_name,
                affected_application_count=other_application_count,
                current_headquarters_display=_location_id_display(
                    connection, current_hq_id
                ),
                new_headquarters_display=_format_location(
                    new_city, new_state_province, new_country
                ),
            )

    connection.execute(
        "UPDATE company SET hq_location_id = ? WHERE company_id = ?",
        (new_hq_id, company_id),
    )


def edit_application(
    connection,
    application_id,
    *,
    company_name,
    job_title,
    application_date: date,
    source_name,
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
    confirm_shared_headquarters_change=False,
) -> EditApplicationResult | None:
    existing = connection.execute(
        "SELECT company_id FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    if existing is None:
        return None
    original_company_id = existing["company_id"]

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
        company_id, is_new_company = _resolve_or_create_company(
            connection, company_name
        )
        company_reassigned = company_id != original_company_id

        if company_reassigned:
            # architecture.md: "Changing an application's company shall
            # ... display the selected company's headquarters rather than
            # carry over the previous company's headquarters." Submitted
            # headquarters fields on this same request may be stale values
            # left over from the company being replaced (the form has no
            # way to refresh them without a round trip), so never apply
            # them as part of a reassignment - the new/target company's own
            # headquarters (None for a brand-new company) is used as-is.
            # Editing that company's headquarters is a separate, subsequent
            # edit, once the form reflects its real current value.
            pass
        else:
            _apply_company_headquarters_change(
                connection,
                company_id,
                is_new_company,
                company_hq_location,
                application_id,
                confirm_shared_headquarters_change,
            )
        source_id = _resolve_or_create_source(connection, source_name)
        job_location_id = _resolve_or_create_location(connection, job_location)

        connection.execute(
            """
            UPDATE application SET
                company_id = ?,
                job_location_id = ?,
                source_id = ?,
                job_title = ?,
                external_job_id = ?,
                job_url = ?,
                job_description = ?,
                work_arrangement = ?,
                employment_type = ?,
                compensation_min = ?,
                compensation_max = ?,
                compensation_basis = ?,
                application_date = ?,
                notes = ?
            WHERE application_id = ?
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
                application_id,
            ),
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return EditApplicationResult(
        application_id=application_id,
        company_id=company_id,
        source_id=source_id,
        job_location_id=job_location_id,
        company_reassigned=company_reassigned,
    )


@dataclass
class ChangeStatusResult:
    application_id: int
    status_id: int
    status_history_id: int


def change_application_status(
    connection,
    application_id,
    *,
    status_name,
    effective_at: datetime | None = None,
    notes=None,
    now: datetime | None = None,
) -> ChangeStatusResult | None:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    existing = connection.execute(
        "SELECT application_id FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    if existing is None:
        return None

    status_name = _require_text("status_name", status_name)
    if effective_at is None:
        raise ValidationError("effective_at", "is required")
    effective_at = _reject_future_effective_at("effective_at", effective_at, now)

    try:
        status_id = _resolve_status_id(connection, status_name, field="status_name")

        cursor = connection.execute(
            """
            INSERT INTO application_status_history (
                application_id, status_id, effective_at, notes
            ) VALUES (?, ?, ?, ?)
            """,
            (application_id, status_id, _format_timestamp(effective_at), notes),
        )
        status_history_id = cursor.lastrowid

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return ChangeStatusResult(
        application_id=application_id,
        status_id=status_id,
        status_history_id=status_history_id,
    )


class LastRemainingStatusHistoryRecordError(Exception):
    """Raised when attempting to delete an application's only remaining
    status-history record. FR-008: every application must always retain at
    least one."""

    def __init__(self, application_id):
        super().__init__(
            f"Cannot delete the only remaining status history record for "
            f"application {application_id}"
        )
        self.application_id = application_id


def _get_status_history_entry(connection, application_id, history_id):
    return connection.execute(
        "SELECT application_status_history_id FROM application_status_history "
        "WHERE application_status_history_id = ? AND application_id = ?",
        (history_id, application_id),
    ).fetchone()


@dataclass
class CorrectStatusHistoryResult:
    application_id: int
    application_status_history_id: int
    status_id: int


def correct_status_history(
    connection,
    application_id,
    history_id,
    *,
    status_name,
    effective_at: datetime | None = None,
    notes=None,
    now: datetime | None = None,
) -> CorrectStatusHistoryResult | None:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if _get_status_history_entry(connection, application_id, history_id) is None:
        return None

    status_name = _require_text("status_name", status_name)
    if effective_at is None:
        raise ValidationError("effective_at", "is required")
    effective_at = _reject_future_effective_at("effective_at", effective_at, now)

    try:
        status_id = _resolve_status_id(connection, status_name, field="status_name")

        connection.execute(
            """
            UPDATE application_status_history
               SET status_id = ?, effective_at = ?, notes = ?
             WHERE application_status_history_id = ?
            """,
            (status_id, _format_timestamp(effective_at), notes, history_id),
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return CorrectStatusHistoryResult(
        application_id=application_id,
        application_status_history_id=history_id,
        status_id=status_id,
    )


@dataclass
class DeleteStatusHistoryResult:
    application_id: int
    deleted_history_id: int


def delete_status_history(
    connection, application_id, history_id
) -> DeleteStatusHistoryResult | None:
    if _get_status_history_entry(connection, application_id, history_id) is None:
        return None

    try:
        remaining_count = connection.execute(
            "SELECT COUNT(*) AS n FROM application_status_history "
            "WHERE application_id = ?",
            (application_id,),
        ).fetchone()["n"]
        if remaining_count <= 1:
            raise LastRemainingStatusHistoryRecordError(application_id)

        connection.execute(
            "DELETE FROM application_status_history "
            "WHERE application_status_history_id = ?",
            (history_id,),
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return DeleteStatusHistoryResult(
        application_id=application_id, deleted_history_id=history_id
    )


@dataclass
class ArchiveApplicationResult:
    application_id: int


def archive_application(
    connection, application_id, now: datetime | None = None
) -> ArchiveApplicationResult | None:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    existing = connection.execute(
        "SELECT application_id FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    if existing is None:
        return None

    try:
        # Only set archived_at when currently unset, so archiving an
        # already-archived application is a true no-op (preserves the
        # original archive time and leaves last_updated_at untouched via
        # the existing no-op-safe trigger) rather than repeatedly bumping it.
        connection.execute(
            """
            UPDATE application
               SET archived_at = ?
             WHERE application_id = ? AND archived_at IS NULL
            """,
            (_format_timestamp(now), application_id),
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return ArchiveApplicationResult(application_id=application_id)


@dataclass
class RestoreApplicationResult:
    application_id: int


def restore_application(connection, application_id) -> RestoreApplicationResult | None:
    existing = connection.execute(
        "SELECT application_id FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    if existing is None:
        return None

    try:
        # Only clear archived_at when currently set, so restoring an
        # already-active application is a true no-op.
        connection.execute(
            """
            UPDATE application
               SET archived_at = NULL
             WHERE application_id = ? AND archived_at IS NOT NULL
            """,
            (application_id,),
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return RestoreApplicationResult(application_id=application_id)
