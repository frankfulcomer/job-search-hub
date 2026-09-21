from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    PotentialDuplicateApplicationsDetected,
    archive_application,
    create_application,
)

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
        "application_date": date(2026, 9, 18),
        "source_name": "Job Board",
        "initial_status_effective_at": datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        "now": NOW,
    }
    fields.update(overrides)
    return create_application(connection, **fields)


def test_no_warning_when_no_similar_application_exists(connection):
    result = _create(connection)
    assert result.application_id is not None


def test_no_warning_for_first_application_with_external_job_id(connection):
    result = _create(connection, external_job_id="REQ-1")
    assert result.application_id is not None


def test_raises_for_same_company_and_external_job_id(connection):
    _create(connection, external_job_id="REQ-1")

    with pytest.raises(PotentialDuplicateApplicationsDetected):
        _create(
            connection,
            job_title="A Completely Different Title",
            external_job_id="REQ-1",
        )


def test_external_job_id_match_is_case_and_whitespace_insensitive(connection):
    _create(connection, external_job_id="REQ-1")

    with pytest.raises(PotentialDuplicateApplicationsDetected):
        _create(connection, external_job_id="  req-1  ")


def test_company_match_is_case_and_whitespace_insensitive(connection):
    _create(connection, company_name="Acme Corp", external_job_id="REQ-1")

    with pytest.raises(PotentialDuplicateApplicationsDetected):
        _create(connection, company_name="  ACME corp ", external_job_id="REQ-1")


def test_no_match_when_external_job_id_differs(connection):
    _create(connection, external_job_id="REQ-1")

    result = _create(connection, external_job_id="REQ-2")
    assert result.application_id is not None


def test_no_match_when_company_differs_even_with_same_external_job_id(connection):
    _create(connection, company_name="Acme Corp", external_job_id="REQ-1")

    result = _create(connection, company_name="Globex", external_job_id="REQ-1")
    assert result.application_id is not None


def test_raises_for_same_company_and_job_title_when_no_external_job_id(connection):
    _create(connection)

    with pytest.raises(PotentialDuplicateApplicationsDetected):
        _create(connection)


def test_no_match_when_job_title_differs_and_no_external_job_id(connection):
    _create(connection, job_title="Engineer")

    result = _create(connection, job_title="Manager")
    assert result.application_id is not None


def test_no_match_when_company_differs_even_with_same_job_title(connection):
    _create(connection, company_name="Acme Corp", job_title="Engineer")

    result = _create(connection, company_name="Globex", job_title="Engineer")
    assert result.application_id is not None


def test_job_title_fallback_does_not_apply_when_new_entry_has_an_external_job_id(
    connection,
):
    # The existing application matches on company + job title, but the new
    # entry supplies its own external_job_id, so only the (non-matching)
    # external-ID indicator is checked - the job-title fallback is only used
    # "when an identifier is unavailable" (architecture.md).
    _create(connection, company_name="Acme Corp", job_title="Engineer")

    result = _create(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        external_job_id="REQ-1",
    )
    assert result.application_id is not None


def test_matches_include_archived_applications(connection):
    original = _create(connection, external_job_id="REQ-1")
    archive_application(connection, original.application_id, now=NOW)

    with pytest.raises(PotentialDuplicateApplicationsDetected) as exc_info:
        _create(connection, external_job_id="REQ-1")

    assert exc_info.value.matches[0].is_archived is True


def test_confirm_duplicate_bypasses_the_check_and_saves(connection):
    _create(connection, external_job_id="REQ-1")

    result = _create(connection, external_job_id="REQ-1", confirm_duplicate=True)

    assert result.application_id is not None


def test_duplicate_warned_attempt_creates_no_reference_data(connection):
    _create(connection, external_job_id="REQ-1")
    before_companies = connection.execute(
        "SELECT COUNT(*) AS n FROM company"
    ).fetchone()["n"]
    before_sources = connection.execute(
        "SELECT COUNT(*) AS n FROM source"
    ).fetchone()["n"]

    with pytest.raises(PotentialDuplicateApplicationsDetected):
        _create(
            connection,
            company_name="Acme Corp",
            source_name="A Brand New Source",
            external_job_id="REQ-1",
        )

    after_companies = connection.execute(
        "SELECT COUNT(*) AS n FROM company"
    ).fetchone()["n"]
    after_sources = connection.execute(
        "SELECT COUNT(*) AS n FROM source"
    ).fetchone()["n"]
    assert after_companies == before_companies
    assert after_sources == before_sources


def test_duplicate_warned_attempt_does_not_persist_an_application(connection):
    _create(connection, external_job_id="REQ-1")
    before_count = connection.execute(
        "SELECT COUNT(*) AS n FROM application"
    ).fetchone()["n"]

    with pytest.raises(PotentialDuplicateApplicationsDetected):
        _create(connection, external_job_id="REQ-1")

    after_count = connection.execute(
        "SELECT COUNT(*) AS n FROM application"
    ).fetchone()["n"]
    assert after_count == before_count


def test_all_matches_are_returned(connection):
    first = _create(
        connection, application_date=date(2026, 9, 16), external_job_id="REQ-1"
    )
    archive_application(connection, first.application_id, now=NOW)
    second = _create(
        connection,
        application_date=date(2026, 9, 17),
        external_job_id="REQ-1",
        confirm_duplicate=True,
    )

    with pytest.raises(PotentialDuplicateApplicationsDetected) as exc_info:
        _create(connection, external_job_id="REQ-1")

    matched_ids = {match.application_id for match in exc_info.value.matches}
    assert matched_ids == {first.application_id, second.application_id}


def test_match_fields_reflect_the_existing_application(connection):
    _create(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 18),
        external_job_id="REQ-1",
    )

    with pytest.raises(PotentialDuplicateApplicationsDetected) as exc_info:
        _create(connection, external_job_id="REQ-1")

    match = exc_info.value.matches[0]
    assert match.company_name == "Acme Corp"
    assert match.job_title == "Engineer"
    assert match.application_date == "2026-09-18"
    assert match.current_status_name == "APPLIED"
    assert match.is_archived is False
