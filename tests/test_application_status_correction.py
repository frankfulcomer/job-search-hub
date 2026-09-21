import sqlite3
from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    LastRemainingStatusHistoryRecordError,
    ValidationError,
    change_application_status,
    correct_status_history,
    create_application,
    delete_status_history,
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


def _add_screening(connection, application_id):
    change_application_status(
        connection,
        application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )


# --- correct_status_history ---------------------------------------------


def test_correct_returns_none_for_nonexistent_application_id(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    outcome = correct_status_history(
        connection,
        999999,
        history_id,
        status_name="SCREENING",
        effective_at=NOW,
        now=NOW,
    )
    assert outcome is None


def test_correct_returns_none_for_nonexistent_history_id(connection):
    result = _create(connection)

    outcome = correct_status_history(
        connection,
        result.application_id,
        999999,
        status_name="SCREENING",
        effective_at=NOW,
        now=NOW,
    )
    assert outcome is None


def test_correct_returns_none_when_history_id_belongs_to_other_application(
    connection,
):
    first = _create(connection)
    second = _create(connection, company_name="Globex", job_title="Analyst")
    other_history_id = get_application_detail(
        connection, second.application_id
    ).status_history[0].application_status_history_id

    outcome = correct_status_history(
        connection,
        first.application_id,
        other_history_id,
        status_name="SCREENING",
        effective_at=NOW,
        now=NOW,
    )
    assert outcome is None


def test_correct_updates_status_effective_at_and_notes(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    correct_status_history(
        connection,
        result.application_id,
        history_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 18, 11, 0, tzinfo=timezone.utc),
        notes="Corrected entry",
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert len(detail.status_history) == 1
    entry = detail.status_history[0]
    assert entry.status_name == "SCREENING"
    assert entry.notes == "Corrected entry"
    assert entry.application_status_history_id == history_id


def test_correct_current_entry_recalculates_current_status(connection):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    current_id = get_application_detail(
        connection, result.application_id
    ).status_history[-1].application_status_history_id

    correct_status_history(
        connection,
        result.application_id,
        current_id,
        status_name="INTERVIEWING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.current_status_name == "INTERVIEWING"


def test_correct_non_current_entry_does_not_change_current_status(connection):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    original_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    correct_status_history(
        connection,
        result.application_id,
        original_id,
        status_name="APPLIED",
        effective_at=datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc),
        notes="Earlier than originally recorded",
        now=NOW,
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.current_status_name == "SCREENING"


def test_correct_future_effective_at_is_rejected(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    with pytest.raises(ValidationError) as exc_info:
        correct_status_history(
            connection,
            result.application_id,
            history_id,
            status_name="SCREENING",
            effective_at=datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc),
            now=NOW,
        )
    assert exc_info.value.field == "effective_at"


def test_correct_missing_effective_at_is_rejected(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    with pytest.raises(ValidationError) as exc_info:
        correct_status_history(
            connection,
            result.application_id,
            history_id,
            status_name="SCREENING",
            now=NOW,
        )
    assert exc_info.value.field == "effective_at"


def test_correct_blank_status_name_is_rejected(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    with pytest.raises(ValidationError) as exc_info:
        correct_status_history(
            connection,
            result.application_id,
            history_id,
            status_name="   ",
            effective_at=NOW,
            now=NOW,
        )
    assert exc_info.value.field == "status_name"


def test_correct_unknown_status_name_is_rejected(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    with pytest.raises(ValidationError) as exc_info:
        correct_status_history(
            connection,
            result.application_id,
            history_id,
            status_name="NOT_A_REAL_STATUS",
            effective_at=NOW,
            now=NOW,
        )
    assert exc_info.value.field == "status_name"


def test_correct_duplicate_effective_at_raises_integrity_error_and_persists_nothing(
    connection,
):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    original_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id
    before = get_application_detail(connection, result.application_id).status_history

    with pytest.raises(sqlite3.IntegrityError):
        correct_status_history(
            connection,
            result.application_id,
            original_id,
            status_name="APPLIED",
            effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),  # collides
            now=NOW,
        )

    after = get_application_detail(connection, result.application_id).status_history
    assert [(e.status_name, e.effective_at) for e in after] == [
        (e.status_name, e.effective_at) for e in before
    ]


def test_correct_does_not_modify_last_updated_at_on_application(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id
    before = connection.execute(
        "SELECT last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["last_updated_at"]

    correct_status_history(
        connection,
        result.application_id,
        history_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    after = connection.execute(
        "SELECT last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["last_updated_at"]
    assert after == before


def test_correct_preserves_created_at_and_advances_last_updated_at_on_history_row(
    connection,
):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id
    before = connection.execute(
        "SELECT created_at, last_updated_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (history_id,),
    ).fetchone()

    import time

    time.sleep(0.01)
    correct_status_history(
        connection,
        result.application_id,
        history_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    after = connection.execute(
        "SELECT created_at, last_updated_at FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (history_id,),
    ).fetchone()
    assert after["created_at"] == before["created_at"]
    assert after["last_updated_at"] > before["last_updated_at"]


# --- delete_status_history ------------------------------------------------


def test_delete_returns_none_for_nonexistent_application_id(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    outcome = delete_status_history(connection, 999999, history_id)
    assert outcome is None


def test_delete_returns_none_for_nonexistent_history_id(connection):
    result = _create(connection)

    outcome = delete_status_history(connection, result.application_id, 999999)
    assert outcome is None


def test_delete_returns_none_when_history_id_belongs_to_other_application(
    connection,
):
    first = _create(connection)
    second = _create(connection, company_name="Globex", job_title="Analyst")
    other_history_id = get_application_detail(
        connection, second.application_id
    ).status_history[0].application_status_history_id

    outcome = delete_status_history(connection, first.application_id, other_history_id)
    assert outcome is None

    # Confirm the other application's entry was left untouched, not deleted.
    detail = get_application_detail(connection, second.application_id)
    assert len(detail.status_history) == 1
    assert detail.status_history[0].application_status_history_id == other_history_id


def test_delete_non_current_entry_removes_it(connection):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    original_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    delete_status_history(connection, result.application_id, original_id)

    detail = get_application_detail(connection, result.application_id)
    assert len(detail.status_history) == 1
    assert detail.status_history[0].status_name == "SCREENING"


def test_delete_current_entry_falls_back_to_next_most_recent(connection):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    current_id = get_application_detail(
        connection, result.application_id
    ).status_history[-1].application_status_history_id

    delete_status_history(connection, result.application_id, current_id)

    detail = get_application_detail(connection, result.application_id)
    assert len(detail.status_history) == 1
    assert detail.current_status_name == "APPLIED"


def test_delete_only_remaining_entry_is_blocked(connection):
    result = _create(connection)
    history_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    with pytest.raises(LastRemainingStatusHistoryRecordError):
        delete_status_history(connection, result.application_id, history_id)

    detail = get_application_detail(connection, result.application_id)
    assert len(detail.status_history) == 1
    assert detail.status_history[0].application_status_history_id == history_id


def test_delete_does_not_modify_last_updated_at_on_application(connection):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    original_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id
    before = connection.execute(
        "SELECT last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["last_updated_at"]

    delete_status_history(connection, result.application_id, original_id)

    after = connection.execute(
        "SELECT last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["last_updated_at"]
    assert after == before


def test_delete_does_not_modify_archived_at(connection):
    result = _create(connection)
    _add_screening(connection, result.application_id)
    original_id = get_application_detail(
        connection, result.application_id
    ).status_history[0].application_status_history_id

    delete_status_history(connection, result.application_id, original_id)

    archived_at = connection.execute(
        "SELECT archived_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["archived_at"]
    assert archived_at is None
