import time
from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    archive_application,
    create_application,
    get_application_detail,
    restore_application,
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


# --- archive_application ----------------------------------------------


def test_archive_returns_none_for_nonexistent_application(connection):
    outcome = archive_application(connection, 999999, now=NOW)
    assert outcome is None


def test_archive_sets_archived_at(connection):
    result = _create(connection)

    outcome = archive_application(connection, result.application_id, now=NOW)

    assert outcome.application_id == result.application_id
    detail = get_application_detail(connection, result.application_id)
    assert detail.is_archived is True
    assert detail.archived_at is not None


def test_archive_records_the_actual_archive_time(connection):
    result = _create(connection)

    archive_application(connection, result.application_id, now=NOW)

    detail = get_application_detail(connection, result.application_id)
    assert detail.archived_at == "2026-09-20T15:00:00.000Z"


def test_archive_preserves_created_at_and_advances_last_updated_at(connection):
    result = _create(connection)
    before = connection.execute(
        "SELECT created_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    time.sleep(0.01)
    archive_application(connection, result.application_id, now=NOW)

    after = connection.execute(
        "SELECT created_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["created_at"] == before["created_at"]
    assert after["last_updated_at"] > before["last_updated_at"]


def test_archive_preserves_application_information_and_status_history(connection):
    result = _create(connection, notes="Original notes")

    archive_application(connection, result.application_id, now=NOW)

    detail = get_application_detail(connection, result.application_id)
    assert detail.notes == "Original notes"
    assert detail.job_title == "Engineer"
    assert len(detail.status_history) == 1
    assert detail.current_status_name == "APPLIED"


def test_archive_removes_application_from_default_list(connection):
    from job_hub.applications import list_applications

    result = _create(connection)
    archive_application(connection, result.application_id, now=NOW)

    listed = list_applications(connection)

    assert listed.items == []


def test_archiving_already_archived_application_is_a_true_noop(connection):
    result = _create(connection)
    archive_application(connection, result.application_id, now=NOW)
    before = connection.execute(
        "SELECT archived_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    time.sleep(0.01)
    archive_application(
        connection,
        result.application_id,
        now=datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc),
    )

    after = connection.execute(
        "SELECT archived_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["archived_at"] == before["archived_at"]
    assert after["last_updated_at"] == before["last_updated_at"]


# --- restore_application -------------------------------------------------


def test_restore_returns_none_for_nonexistent_application(connection):
    outcome = restore_application(connection, 999999)
    assert outcome is None


def test_restore_clears_archived_at(connection):
    result = _create(connection)
    archive_application(connection, result.application_id, now=NOW)

    outcome = restore_application(connection, result.application_id)

    assert outcome.application_id == result.application_id
    detail = get_application_detail(connection, result.application_id)
    assert detail.is_archived is False
    assert detail.archived_at is None


def test_restore_preserves_created_at_and_advances_last_updated_at(connection):
    result = _create(connection)
    archive_application(connection, result.application_id, now=NOW)
    before = connection.execute(
        "SELECT created_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    time.sleep(0.01)
    restore_application(connection, result.application_id)

    after = connection.execute(
        "SELECT created_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["created_at"] == before["created_at"]
    assert after["last_updated_at"] > before["last_updated_at"]


def test_restore_preserves_application_information_and_status_history(connection):
    result = _create(connection, notes="Original notes")
    archive_application(connection, result.application_id, now=NOW)

    restore_application(connection, result.application_id)

    detail = get_application_detail(connection, result.application_id)
    assert detail.notes == "Original notes"
    assert len(detail.status_history) == 1
    assert detail.current_status_name == "APPLIED"


def test_restore_returns_application_to_default_list(connection):
    from job_hub.applications import list_applications

    result = _create(connection)
    archive_application(connection, result.application_id, now=NOW)

    restore_application(connection, result.application_id)

    listed = list_applications(connection)
    assert [item.application_id for item in listed.items] == [result.application_id]


def test_restoring_already_active_application_is_a_true_noop(connection):
    result = _create(connection)
    before = connection.execute(
        "SELECT archived_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    time.sleep(0.01)
    restore_application(connection, result.application_id)

    after = connection.execute(
        "SELECT archived_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["archived_at"] is None
    assert after["last_updated_at"] == before["last_updated_at"]


def test_archive_then_restore_does_not_modify_other_application_fields(connection):
    result = _create(connection, job_title="Engineer", company_name="Acme Corp")
    before = connection.execute(
        "SELECT job_title, application_date FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    archive_application(connection, result.application_id, now=NOW)
    restore_application(connection, result.application_id)

    after = connection.execute(
        "SELECT job_title, application_date FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["job_title"] == before["job_title"]
    assert after["application_date"] == before["application_date"]
