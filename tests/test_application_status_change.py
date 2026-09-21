import sqlite3
from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    ValidationError,
    change_application_status,
    create_application,
    get_application_detail,
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


def test_change_status_returns_none_for_nonexistent_id(connection):
    result = change_application_status(
        connection, 999, status_name="SCREENING", effective_at=NOW
    )
    assert result is None


def test_change_status_creates_new_history_record(connection):
    result = _create(connection)

    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert len(detail.status_history) == 2
    assert [entry.status_name for entry in detail.status_history] == [
        "APPLIED",
        "SCREENING",
    ]


def test_change_status_does_not_overwrite_existing_history(connection):
    result = _create(connection)
    original_entry = get_application_detail(
        connection, result.application_id
    ).status_history[0]

    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    preserved_entry = detail.status_history[0]
    assert preserved_entry.status_name == original_entry.status_name
    assert preserved_entry.effective_at == original_entry.effective_at
    assert preserved_entry.application_status_history_id == (
        original_entry.application_status_history_id
    )


def test_change_status_becomes_current_when_most_recent(connection):
    result = _create(connection)

    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.current_status_name == "SCREENING"


def test_backdated_status_change_does_not_become_current(connection):
    result = _create(connection)
    # Establish SCREENING as current (2026-09-19 10:00), later than the
    # initial APPLIED entry (2026-09-18 09:00).
    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    # Insert a status change effective BEFORE the current SCREENING entry.
    change_application_status(
        connection,
        result.application_id,
        status_name="ACCEPTED",
        effective_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.current_status_name == "SCREENING"
    assert len(detail.status_history) == 3


def test_backdated_status_change_is_recorded_in_history_in_correct_order(connection):
    result = _create(connection)
    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )
    change_application_status(
        connection,
        result.application_id,
        status_name="ACCEPTED",
        effective_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert [entry.status_name for entry in detail.status_history] == [
        "APPLIED",
        "ACCEPTED",
        "SCREENING",
    ]
    current_flags = [entry.is_current for entry in detail.status_history]
    assert current_flags == [False, False, True]


def test_reselecting_current_status_is_a_legitimate_new_event(connection):
    result = _create(connection)

    change_application_status(
        connection,
        result.application_id,
        status_name="APPLIED",
        effective_at=datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc),
        notes="Following up, still applied",
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert len(detail.status_history) == 2
    assert detail.current_status_name == "APPLIED"
    assert detail.status_history[-1].notes == "Following up, still applied"


def test_future_effective_at_is_rejected(connection):
    result = _create(connection)

    with pytest.raises(ValidationError) as exc_info:
        change_application_status(
            connection,
            result.application_id,
            status_name="SCREENING",
            effective_at=datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc),
            now=NOW,
        )
    assert exc_info.value.field == "effective_at"


def test_missing_effective_at_is_rejected(connection):
    result = _create(connection)

    with pytest.raises(ValidationError) as exc_info:
        change_application_status(
            connection, result.application_id, status_name="SCREENING", now=NOW
        )
    assert exc_info.value.field == "effective_at"


def test_blank_status_name_is_rejected(connection):
    result = _create(connection)

    with pytest.raises(ValidationError) as exc_info:
        change_application_status(
            connection, result.application_id, status_name="   ", effective_at=NOW, now=NOW
        )
    assert exc_info.value.field == "status_name"


def test_unknown_status_name_is_rejected(connection):
    result = _create(connection)

    with pytest.raises(ValidationError) as exc_info:
        change_application_status(
            connection,
            result.application_id,
            status_name="NOT_A_REAL_STATUS",
            effective_at=NOW,
            now=NOW,
        )
    assert exc_info.value.field == "status_name"


def test_duplicate_effective_at_raises_integrity_error_and_persists_nothing(
    connection,
):
    result = _create(connection)
    before = get_application_detail(connection, result.application_id).status_history

    with pytest.raises(sqlite3.IntegrityError):
        change_application_status(
            connection,
            result.application_id,
            status_name="SCREENING",
            effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),  # collides
            now=NOW,
        )

    after = get_application_detail(connection, result.application_id).status_history
    assert len(after) == len(before) == 1


def test_created_at_and_last_updated_at_set_for_new_history_row(connection):
    result = _create(connection)

    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    row = connection.execute(
        "SELECT created_at, last_updated_at FROM application_status_history "
        "ORDER BY application_status_history_id DESC LIMIT 1"
    ).fetchone()
    assert row["created_at"] == row["last_updated_at"]
    assert row["created_at"].endswith("Z")


def test_does_not_modify_application_row_fields(connection):
    result = _create(connection)
    before = connection.execute(
        "SELECT job_title, application_date, archived_at, last_updated_at "
        "FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    change_application_status(
        connection,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    after = connection.execute(
        "SELECT job_title, application_date, archived_at, last_updated_at "
        "FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["job_title"] == before["job_title"]
    assert after["application_date"] == before["application_date"]
    assert after["archived_at"] is None
    assert before["archived_at"] is None
    assert after["last_updated_at"] == before["last_updated_at"]
