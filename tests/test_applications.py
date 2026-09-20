import sqlite3
from datetime import date, datetime, timezone

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
    with pytest.raises(sqlite3.IntegrityError):
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


def test_transaction_rolls_back_completely_on_later_database_failure(connection):
    before = _counts(connection)

    with pytest.raises(sqlite3.IntegrityError):
        create_application(
            connection,
            company_name="Brand New Company",
            job_title="Engineer",
            application_date=date(2026, 9, 20),
            source_name="Brand New Source",
            compensation_min=200000,
            compensation_max=100000,
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
