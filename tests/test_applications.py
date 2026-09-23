import sqlite3
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from job_hub import db
from job_hub.applications import (
    LocationInput,
    ValidationError,
    create_application,
)

NOW = datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def connection(tmp_path):
    conn = db.connect(str(tmp_path / "test.sqlite3"))
    db.init_db(conn)
    yield conn
    conn.close()


def _counts(connection):
    tables = ["company", "source", "location", "application", "application_status_history"]
    return {
        table: connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        for table in tables
    }


def test_successful_application_creation(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        now=NOW,
    )

    row = connection.execute(
        "SELECT * FROM application WHERE application_id = ?", (result.application_id,)
    ).fetchone()

    assert row["job_title"] == "Engineer"
    assert row["company_id"] == result.company_id
    assert row["source_id"] == result.source_id
    assert row["application_date"] == "2026-09-20"


def test_initial_status_and_history_creation(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        now=NOW,
    )

    status = connection.execute(
        "SELECT name FROM status WHERE status_id = ?", (result.initial_status_id,)
    ).fetchone()
    history = connection.execute(
        "SELECT application_id, status_id, effective_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (result.status_history_id,),
    ).fetchone()

    assert status["name"] == "APPLIED"
    assert history["application_id"] == result.application_id
    assert history["status_id"] == result.initial_status_id
    assert history["effective_at"] == "2026-09-20T15:00:00.000Z"


def test_default_status_and_effective_at_when_application_date_is_today(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=NOW.date(),
        source_name="Job Board",
        now=NOW,
    )

    history = connection.execute(
        "SELECT effective_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (result.status_history_id,),
    ).fetchone()

    assert history["effective_at"] == "2026-09-20T15:00:00.000Z"


def test_default_now_is_constructed_as_local_not_utc(connection):
    # Deterministic regression test for a real bug: create_application's
    # default `now` (used whenever a caller omits it, i.e. every real
    # request via the Flask routes) was constructed as
    # `datetime.now(timezone.utc)`, but application_date comes from the
    # create form's date.today() default, which is local. For several
    # hours daily in any negative-UTC-offset timezone, UTC's calendar day
    # is already ahead of local, so an ordinary "create for today with the
    # default APPLIED status" submission incorrectly required an explicit
    # effective time it shouldn't need.
    #
    # This exercises the exact default-construction code path (no `now`
    # argument is passed, so `now or datetime.now().astimezone()` must
    # execute) and asserts on the *call signature* used, not on wall-clock
    # timing or a simulated outcome. `wraps=datetime` keeps all real
    # datetime behavior intact (the rest of create_application runs
    # normally) while recording how `datetime.now` was invoked. If the old
    # `datetime.now(timezone.utc)` default were restored, `now` would be
    # called with one positional argument and this assertion would fail,
    # regardless of the real time or timezone the test happens to run in.
    with patch("job_hub.applications.datetime", wraps=datetime) as mock_datetime:
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date.today(),
            source_name="Job Board",
        )

    mock_datetime.now.assert_called_once_with()


def test_default_now_uses_local_today_not_utc_today(connection):
    # Complementary end-to-end sanity check using the real, unmocked
    # default: confirms the real system clock and real local timezone
    # produce a working "create for today" submission. Not a reliable
    # regression guard on its own - it only reliably fails under the old
    # buggy default during the UTC/local calendar-boundary window, so it
    # can silently pass under old *and* new code outside that window. The
    # deterministic call-signature test above is what actually protects
    # against reintroducing the bug at any time of day.
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date.today(),
        source_name="Job Board",
    )

    detail_status = connection.execute(
        "SELECT name FROM status WHERE status_id = ?", (result.initial_status_id,)
    ).fetchone()["name"]
    assert detail_status == "APPLIED"


def test_today_comparison_respects_nows_own_timezone_not_utc(connection):
    # Verifies a related but distinct property: the "is application_date
    # today" comparison uses whatever local-meaning timezone an explicitly
    # passed `now` carries, rather than assuming UTC. Because `now` is
    # passed explicitly here, `now or <default>` never evaluates the
    # default expression, so this does NOT exercise or guard the
    # default-construction bug above (a hardcoded-UTC default would pass
    # this test identically) - it guards a different possible regression,
    # in the comparison itself rather than in what `now` defaults to.
    local_now = datetime(2026, 9, 20, 23, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert local_now.astimezone(timezone.utc).date() == date(2026, 9, 21)

    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),  # matches local_now's own date
        source_name="Job Board",
        now=local_now,
    )

    history = connection.execute(
        "SELECT effective_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (result.status_history_id,),
    ).fetchone()
    assert history["effective_at"] is not None


def test_retrospective_initial_status_uses_supplied_status_and_effective_at(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 1),
        source_name="Job Board",
        initial_status_name="INTERVIEWING",
        initial_status_effective_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    status = connection.execute(
        "SELECT name FROM status WHERE status_id = ?", (result.initial_status_id,)
    ).fetchone()
    history = connection.execute(
        "SELECT effective_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (result.status_history_id,),
    ).fetchone()

    assert status["name"] == "INTERVIEWING"
    assert history["effective_at"] == "2026-09-10T12:00:00.000Z"


def test_missing_required_effective_at_for_non_today_application_date_raises(connection):
    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 1),
            source_name="Job Board",
            now=NOW,
        )


def test_timezone_naive_now_override_does_not_raise_type_error(connection):
    naive_now = datetime(2026, 9, 20, 15, 0, 0)

    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        now=naive_now,
    )

    history = connection.execute(
        "SELECT effective_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (result.status_history_id,),
    ).fetchone()
    assert history["effective_at"] == "2026-09-20T15:00:00.000Z"


def test_future_effective_at_raises_validation_error(connection):
    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            initial_status_effective_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
            now=NOW,
        )


def test_unknown_initial_status_name_raises_validation_error(connection):
    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            initial_status_name="NOT_A_REAL_STATUS",
            now=NOW,
        )


def test_reuses_equivalent_company_source_and_location(connection):
    first = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
        now=NOW,
    )

    second = create_application(
        connection,
        company_name="  acme corp  ",
        job_title="Senior Engineer",
        application_date=date(2026, 9, 20),
        source_name=" JOB BOARD ",
        job_location=LocationInput(city=" AUSTIN", state_province="tx ", country="usa"),
        now=NOW,
    )

    assert second.company_id == first.company_id
    assert second.source_id == first.source_id
    assert second.job_location_id == first.job_location_id
    assert _counts(connection)["company"] == 1
    assert _counts(connection)["source"] == 1
    assert _counts(connection)["location"] == 1


def test_creates_new_reference_records_when_no_equivalent_exists(connection):
    create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
        now=NOW,
    )
    second = create_application(
        connection,
        company_name="Globex",
        job_title="Analyst",
        application_date=date(2026, 9, 20),
        source_name="Referral",
        job_location=LocationInput(city="Denver", state_province="CO", country="USA"),
        now=NOW,
    )

    counts = _counts(connection)
    assert counts["company"] == 2
    assert counts["source"] == 2
    assert counts["location"] == 2
    assert second.job_location_id is not None


def test_new_company_headquarters_location_is_created_and_linked(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        company_hq_location=LocationInput(city="Seattle", state_province="WA", country="USA"),
        now=NOW,
    )

    company = connection.execute(
        "SELECT hq_location_id FROM company WHERE company_id = ?", (result.company_id,)
    ).fetchone()
    assert company["hq_location_id"] is not None


def test_existing_company_headquarters_is_not_overwritten(connection):
    first = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        company_hq_location=LocationInput(city="Seattle", state_province="WA", country="USA"),
        now=NOW,
    )
    original_hq = connection.execute(
        "SELECT hq_location_id FROM company WHERE company_id = ?", (first.company_id,)
    ).fetchone()["hq_location_id"]

    create_application(
        connection,
        company_name="Acme Corp",
        job_title="Analyst",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        company_hq_location=LocationInput(city="Chicago", state_province="IL", country="USA"),
        now=NOW,
    )

    hq_after = connection.execute(
        "SELECT hq_location_id FROM company WHERE company_id = ?", (first.company_id,)
    ).fetchone()["hq_location_id"]
    assert hq_after == original_hq
    # No orphan location should have been created for the ignored HQ input.
    assert _counts(connection)["location"] == 1


def test_job_location_is_optional(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        now=NOW,
    )

    assert result.job_location_id is None
    assert _counts(connection)["location"] == 0


def test_source_is_required(connection):
    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="   ",
            now=NOW,
        )


def test_missing_job_title_raises_validation_error_before_any_writes(connection):
    before = _counts(connection)

    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="   ",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            now=NOW,
        )

    assert _counts(connection) == before


def test_invalid_work_arrangement_raises_validation_error_before_any_writes(connection):
    before = _counts(connection)

    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            work_arrangement="FROM_THE_MOON",
            now=NOW,
        )

    assert _counts(connection) == before


def test_database_constraint_failure_raises(connection):
    # compensation_min > compensation_max is now caught earlier by
    # _require_compensation_range (ValidationError, see FR-011 tests
    # below), so this test - which verifies create_application surfaces a
    # genuine *database*-level constraint failure rather than swallowing
    # it - uses a non-numeric compensation value instead. No application-
    # level check validates compensation's numeric type (routes.py's
    # _parse_compensation does that before create_application is ever
    # called), so this still reaches the STRICT table's type rejection at
    # the database layer, same as test_db.py's
    # test_compensation_column_rejects_non_numeric_value.
    with pytest.raises(sqlite3.IntegrityError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_min="not-a-number",
            compensation_basis="ANNUAL",
            now=NOW,
        )


def test_transaction_rolls_back_completely_on_later_database_failure(connection):
    before = _counts(connection)

    # See test_database_constraint_failure_raises above for why a
    # non-numeric compensation value is used here rather than
    # compensation_min > compensation_max.
    with pytest.raises(sqlite3.IntegrityError):
        create_application(
            connection,
            company_name="Brand New Company",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Brand New Source",
            compensation_min="not-a-number",
            compensation_basis="ANNUAL",
            now=NOW,
        )

    after = _counts(connection)
    assert after == before
    assert connection.execute(
        "SELECT 1 FROM company WHERE name = 'Brand New Company'"
    ).fetchone() is None
    assert connection.execute(
        "SELECT 1 FROM source WHERE name = 'Brand New Source'"
    ).fetchone() is None


# --- FR-011: job URL syntactic validation -----------------------------------


@pytest.mark.parametrize(
    "invalid_url",
    [
        "not a url",
        "javascript:alert(document.cookie)",
        "ftp://example.com",
        "example.com",
        "http://",
        "https://",
        "mailto:foo@example.com",
        "http://exa mple.com",
        "http://example.com/has space",
    ],
)
def test_invalid_job_url_raises_validation_error(connection, invalid_url):
    with pytest.raises(ValidationError) as exc_info:
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            job_url=invalid_url,
            now=NOW,
        )
    assert exc_info.value.field == "job_url"


def test_invalid_job_url_raises_before_any_writes(connection):
    before = _counts(connection)

    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            job_url="not a url",
            now=NOW,
        )

    assert _counts(connection) == before


@pytest.mark.parametrize(
    "valid_url",
    [
        "http://example.com",
        "https://example.com/job/123",
        "https://example.com/job?query=1#fragment",
        "https://example.com:8080/path",
    ],
)
def test_valid_job_url_is_accepted(connection, valid_url):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        job_url=valid_url,
        now=NOW,
    )
    assert result.application_id is not None


def test_job_url_with_surrounding_whitespace_is_trimmed_then_validated(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        job_url="   https://example.com/job   ",
        now=NOW,
    )
    row = connection.execute(
        "SELECT job_url FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert row["job_url"] == "https://example.com/job"


def test_blank_job_url_remains_optional(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        job_url="   ",
        now=NOW,
    )
    row = connection.execute(
        "SELECT job_url FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert row["job_url"] is None


def test_missing_job_url_remains_optional(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        now=NOW,
    )
    assert result.application_id is not None


# --- FR-011: compensation basis required when compensation is provided -----


def test_compensation_min_without_basis_raises_validation_error(connection):
    with pytest.raises(ValidationError) as exc_info:
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_min=100000,
            now=NOW,
        )
    assert exc_info.value.field == "compensation_basis"


def test_compensation_max_without_basis_raises_validation_error(connection):
    with pytest.raises(ValidationError) as exc_info:
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_max=150000,
            now=NOW,
        )
    assert exc_info.value.field == "compensation_basis"


def test_compensation_min_and_max_without_basis_raises_validation_error(connection):
    with pytest.raises(ValidationError) as exc_info:
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_min=100000,
            compensation_max=150000,
            now=NOW,
        )
    assert exc_info.value.field == "compensation_basis"


def test_compensation_without_basis_raises_before_any_writes(connection):
    before = _counts(connection)

    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_min=100000,
            now=NOW,
        )

    assert _counts(connection) == before


def test_compensation_with_basis_is_accepted(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        compensation_min=100000,
        compensation_max=150000,
        compensation_basis="ANNUAL",
        now=NOW,
    )
    assert result.application_id is not None


def test_no_compensation_and_no_basis_is_accepted(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        now=NOW,
    )
    assert result.application_id is not None


# --- FR-011: compensation min/max relationship messaging --------------------


def test_compensation_min_exceeds_max_raises_validation_error(connection):
    with pytest.raises(ValidationError) as exc_info:
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_min=200000,
            compensation_max=100000,
            compensation_basis="ANNUAL",
            now=NOW,
        )
    assert exc_info.value.field == "compensation_min"
    assert "compensation_max" in str(exc_info.value)


def test_compensation_min_exceeds_max_raises_before_any_writes(connection):
    before = _counts(connection)

    with pytest.raises(ValidationError):
        create_application(
            connection,
            company_name="Acme Corp",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Job Board",
            compensation_min=200000,
            compensation_max=100000,
            compensation_basis="ANNUAL",
            now=NOW,
        )

    assert _counts(connection) == before


def test_compensation_min_equal_to_max_is_accepted(connection):
    result = create_application(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        compensation_min=100000,
        compensation_max=100000,
        compensation_basis="ANNUAL",
        now=NOW,
    )
    assert result.application_id is not None
