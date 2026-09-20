from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import LocationInput, create_application, get_application_detail

NOW = datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def connection(tmp_path):
    conn = db.connect(str(tmp_path / "test.sqlite3"))
    db.init_db(conn)
    yield conn
    conn.close()


def _create(connection, **overrides):
    fields = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date(2026, 9, 20),
        "source_name": "Job Board",
        "now": NOW,
    }
    fields.update(overrides)
    return create_application(connection, **fields)


def test_get_application_detail_returns_none_for_nonexistent_id(connection):
    assert get_application_detail(connection, 999) is None


def test_get_application_detail_returns_core_fields(connection):
    result = _create(
        connection,
        job_url="https://example.com/job",
        job_description="Build things.",
        notes="Applied via referral.",
        external_job_id="REQ-1",
        work_arrangement="REMOTE",
        employment_type="FULL_TIME",
        compensation_min=100000,
        compensation_max=150000,
        compensation_basis="ANNUAL",
    )

    detail = get_application_detail(connection, result.application_id)

    assert detail.company_name == "Acme Corp"
    assert detail.job_title == "Engineer"
    assert detail.source_name == "Job Board"
    assert detail.application_date == "2026-09-20"
    assert detail.job_url == "https://example.com/job"
    assert detail.job_description == "Build things."
    assert detail.notes == "Applied via referral."
    assert detail.external_job_id == "REQ-1"
    assert detail.work_arrangement == "REMOTE"
    assert detail.employment_type == "FULL_TIME"
    assert detail.compensation_min == 100000
    assert detail.compensation_max == 150000
    assert detail.compensation_basis == "ANNUAL"


def test_get_application_detail_missing_optional_fields_are_none(connection):
    result = _create(connection)

    detail = get_application_detail(connection, result.application_id)

    assert detail.job_url is None
    assert detail.job_description is None
    assert detail.notes is None
    assert detail.external_job_id is None
    assert detail.work_arrangement is None
    assert detail.employment_type is None
    assert detail.compensation_min is None
    assert detail.compensation_max is None
    assert detail.compensation_basis is None
    assert detail.job_location_display is None
    assert detail.company_hq_display is None


def test_job_location_and_company_hq_remain_distinct_even_when_same_location(
    connection,
):
    result = _create(
        connection,
        company_hq_location=LocationInput(
            city="Austin", state_province="TX", country="USA"
        ),
        job_location=LocationInput(
            city="austin", state_province="tx", country="usa"
        ),
    )

    detail = get_application_detail(connection, result.application_id)

    assert detail.company_hq_display == "Austin, TX, USA"
    assert detail.job_location_display == "Austin, TX, USA"


def test_status_history_is_ordered_oldest_to_newest(connection):
    result = _create(connection)
    screening_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'SCREENING'"
    ).fetchone()["status_id"]
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at, notes) VALUES (?, ?, ?, ?)",
        (result.application_id, screening_id, "2026-09-20T16:00:00.000Z", "Call scheduled."),
    )
    connection.commit()

    detail = get_application_detail(connection, result.application_id)

    assert [entry.status_name for entry in detail.status_history] == [
        "APPLIED",
        "SCREENING",
    ]
    assert detail.status_history[1].notes == "Call scheduled."


def test_current_status_reflects_latest_effective_at_not_insertion_order(connection):
    result = _create(connection)
    screening_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'SCREENING'"
    ).fetchone()["status_id"]
    # Insert a retrospective correction with an effective_at BEFORE the
    # initial APPLIED entry - it must not become "current" just because it
    # was inserted most recently.
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
        (result.application_id, screening_id, "2026-09-19T09:00:00.000Z"),
    )
    connection.commit()

    detail = get_application_detail(connection, result.application_id)

    assert detail.current_status_name == "APPLIED"


def test_only_the_latest_history_entry_is_marked_current(connection):
    result = _create(connection)
    screening_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'SCREENING'"
    ).fetchone()["status_id"]
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
        (result.application_id, screening_id, "2026-09-20T16:00:00.000Z"),
    )
    connection.commit()

    detail = get_application_detail(connection, result.application_id)

    current_flags = [entry.is_current for entry in detail.status_history]
    assert current_flags == [False, True]


def test_job_url_is_safe_link_only_for_http_and_https_schemes(connection):
    http_result = _create(connection, job_url="http://example.com/job")
    https_result = _create(
        connection, company_name="Other Co", job_url="https://example.com/job"
    )
    js_result = _create(
        connection,
        company_name="Third Co",
        job_url="javascript:alert(document.cookie)",
    )
    no_url_result = _create(connection, company_name="Fourth Co")

    assert get_application_detail(
        connection, http_result.application_id
    ).job_url_is_safe_link
    assert get_application_detail(
        connection, https_result.application_id
    ).job_url_is_safe_link
    assert not get_application_detail(
        connection, js_result.application_id
    ).job_url_is_safe_link
    assert not get_application_detail(
        connection, no_url_result.application_id
    ).job_url_is_safe_link


def test_compensation_display_strips_trailing_zero_for_whole_numbers(connection):
    result = _create(
        connection,
        compensation_min=100000,
        compensation_max=150000,
        compensation_basis="ANNUAL",
    )

    detail = get_application_detail(connection, result.application_id)

    assert detail.compensation_min_display == "100000"
    assert detail.compensation_max_display == "150000"


def test_compensation_display_preserves_non_whole_numbers(connection):
    result = _create(
        connection, compensation_min=45.5, compensation_basis="HOURLY"
    )

    detail = get_application_detail(connection, result.application_id)

    assert detail.compensation_min_display == "45.5"


def test_get_application_detail_raises_overflow_error_for_out_of_range_id(connection):
    with pytest.raises(OverflowError):
        get_application_detail(connection, 10**30)


def test_compensation_fields_can_be_partially_present(connection):
    result = _create(
        connection, compensation_min=100000, compensation_basis="ANNUAL"
    )

    detail = get_application_detail(connection, result.application_id)

    assert detail.compensation_min == 100000
    assert detail.compensation_max is None
    assert detail.compensation_basis == "ANNUAL"
