from datetime import date, datetime, timezone

import pytest

from job_hub import create_app, db
from job_hub.applications import change_application_status, create_application


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.sqlite3")


@pytest.fixture
def app(db_path):
    class TestConfig:
        DATABASE = db_path
        SECRET_KEY = "test"

    return create_app(TestConfig)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def application(db_path):
    # Set up via the service layer directly with an explicit, fixed `now`,
    # so this fixture is never affected by the real wall clock.
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    result = create_application(
        conn,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    change_application_status(
        conn,
        result.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
        now=now,
    )
    rows = conn.execute(
        "SELECT application_status_history_id FROM application_status_history "
        "WHERE application_id = ? ORDER BY effective_at ASC",
        (result.application_id,),
    ).fetchall()
    conn.close()
    return {
        "application_id": result.application_id,
        "applied_history_id": rows[0]["application_status_history_id"],
        "screening_history_id": rows[1]["application_status_history_id"],
    }


def _correct_form(**overrides):
    form = {
        "status_name": "SCREENING",
        "effective_at": "2026-09-19T11:00",
    }
    form.update(overrides)
    return form


# --- correction form -------------------------------------------------------


def test_get_correct_form_returns_200(client, application):
    response = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit"
    )
    assert response.status_code == 200
    assert b'id="status-correct-form"' in response.data


def test_get_correct_form_for_nonexistent_application_returns_404(client, application):
    response = client.get(
        f"/applications/999999/status/{application['screening_history_id']}/edit"
    )
    assert response.status_code == 404


def test_get_correct_form_for_nonexistent_history_id_returns_404(client, application):
    response = client.get(
        f"/applications/{application['application_id']}/status/999999/edit"
    )
    assert response.status_code == 404


def test_get_correct_form_for_history_id_from_other_application_returns_404(
    client, application, db_path
):
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    other = create_application(
        conn,
        company_name="Globex",
        job_title="Analyst",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    other_history_id = other.status_history_id
    conn.close()

    response = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{other_history_id}/edit"
    )
    assert response.status_code == 404


def test_get_correct_form_prefills_existing_values(client, application):
    body = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit"
    ).data.decode()

    assert 'value="2026-09-19T10:00"' in body
    assert 'value="SCREENING"\n                    selected' in body


def test_detail_page_links_to_correct_page_for_each_entry(client, application):
    body = client.get(f"/applications/{application['application_id']}").data.decode()

    assert (
        f'id="correct-status-history-{application["applied_history_id"]}"' in body
    )
    assert (
        f'id="correct-status-history-{application["screening_history_id"]}"' in body
    )


def test_post_valid_correction_redirects_and_flashes(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit",
        data=_correct_form(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Corrected status history entry" in response.data
    assert b'id="detail-current-status">SCREENING<' in response.data


def test_post_correcting_current_entry_updates_current_status(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit",
        data=_correct_form(status_name="INTERVIEWING"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'id="detail-current-status">INTERVIEWING<' in response.data


def test_post_missing_status_shows_error(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit",
        data=_correct_form(status_name=""),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert 'aria-invalid="true"' in body


def test_post_future_effective_at_shows_error(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit",
        data=_correct_form(effective_at="2030-01-01T00:00"),
    )

    assert response.status_code == 200
    assert 'id="form-error"' in response.data.decode()


def test_post_duplicate_effective_at_shows_generic_error(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit",
        data=_correct_form(effective_at="2026-09-18T09:00"),  # collides with APPLIED
    )

    assert response.status_code == 200
    assert 'id="form-error"' in response.data.decode()


def test_post_correct_for_nonexistent_application_returns_404(client, application):
    response = client.post(
        f"/applications/999999/status/{application['screening_history_id']}/edit",
        data=_correct_form(),
    )
    assert response.status_code == 404


def test_post_correct_does_not_alter_archived_at(client, application, db_path):
    client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit",
        data=_correct_form(),
    )

    conn = db.connect(db_path)
    archived_at = conn.execute(
        "SELECT archived_at FROM application WHERE application_id = ?",
        (application["application_id"],),
    ).fetchone()["archived_at"]
    conn.close()
    assert archived_at is None


def test_cancel_link_on_correct_form_returns_to_detail(client, application):
    body = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/edit"
    ).data.decode()

    assert 'id="cancel-status-correct"' in body
    assert (
        f'href="/applications/{application["application_id"]}">Cancel' in body
    )


# --- deletion ---------------------------------------------------------------


def test_get_delete_confirm_returns_200(client, application):
    response = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{application['applied_history_id']}/delete"
    )
    assert response.status_code == 200
    assert b'id="confirm-status-delete"' in response.data


def test_get_delete_confirm_for_nonexistent_application_returns_404(
    client, application
):
    response = client.get(
        f"/applications/999999/status/{application['applied_history_id']}/delete"
    )
    assert response.status_code == 404


def test_get_delete_confirm_for_nonexistent_history_id_returns_404(client, application):
    response = client.get(
        f"/applications/{application['application_id']}/status/999999/delete"
    )
    assert response.status_code == 404


def test_get_delete_confirm_for_history_id_from_other_application_returns_404(
    client, application, db_path
):
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    other = create_application(
        conn,
        company_name="Globex",
        job_title="Analyst",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    other_history_id = other.status_history_id
    conn.close()

    response = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{other_history_id}/delete"
    )
    assert response.status_code == 404


def test_post_delete_for_history_id_from_other_application_returns_404_and_does_not_delete(
    client, application, db_path
):
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    other = create_application(
        conn,
        company_name="Globex",
        job_title="Analyst",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    other_history_id = other.status_history_id
    conn.close()

    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{other_history_id}/delete"
    )
    assert response.status_code == 404

    conn = db.connect(db_path)
    row = conn.execute(
        "SELECT application_status_history_id FROM application_status_history "
        "WHERE application_status_history_id = ?",
        (other_history_id,),
    ).fetchone()
    conn.close()
    assert row is not None


def test_detail_page_hides_delete_link_when_only_one_entry(client, db_path):
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    result = create_application(
        conn,
        company_name="Solo Corp",
        job_title="Analyst",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    history_id = result.status_history_id
    conn.close()

    body = client.get(f"/applications/{result.application_id}").data.decode()
    assert f'id="correct-status-history-{history_id}"' in body
    assert f'id="delete-status-history-{history_id}"' not in body


def test_detail_page_shows_delete_link_when_multiple_entries(client, application):
    body = client.get(f"/applications/{application['application_id']}").data.decode()

    assert (
        f'id="delete-status-history-{application["applied_history_id"]}"' in body
    )
    assert (
        f'id="delete-status-history-{application["screening_history_id"]}"' in body
    )


def test_get_delete_confirm_for_only_entry_blocks_deletion(client, db_path):
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    result = create_application(
        conn,
        company_name="Solo Corp",
        job_title="Analyst",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    history_id = result.status_history_id
    conn.close()

    response = client.get(
        f"/applications/{result.application_id}/status/{history_id}/delete"
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="status-delete-blocked"' in body
    assert 'id="confirm-status-delete"' not in body


def test_post_delete_last_remaining_entry_is_blocked(client, db_path):
    conn = db.connect(db_path)
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    result = create_application(
        conn,
        company_name="Solo Corp",
        job_title="Analyst",
        application_date=date(2026, 9, 18),
        source_name="Job Board",
        initial_status_effective_at=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        now=now,
    )
    history_id = result.status_history_id
    conn.close()

    response = client.post(
        f"/applications/{result.application_id}/status/{history_id}/delete"
    )
    assert response.status_code == 200
    assert 'id="form-error"' in response.data.decode()

    detail_body = client.get(f"/applications/{result.application_id}").data.decode()
    assert f'id="status-history-row-{history_id}"' in detail_body


def test_post_valid_delete_redirects_and_flashes(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['applied_history_id']}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Deleted status history entry" in response.data
    assert (
        f'id="status-history-row-{application["applied_history_id"]}"'.encode()
        not in response.data
    )


def test_post_delete_current_entry_falls_back_current_status(client, application):
    response = client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['screening_history_id']}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'id="detail-current-status">APPLIED<' in response.data


def test_post_delete_for_nonexistent_application_returns_404(client, application):
    response = client.post(
        f"/applications/999999/status/{application['applied_history_id']}/delete"
    )
    assert response.status_code == 404


def test_post_delete_does_not_alter_archived_at(client, application, db_path):
    client.post(
        f"/applications/{application['application_id']}/status/"
        f"{application['applied_history_id']}/delete"
    )

    conn = db.connect(db_path)
    archived_at = conn.execute(
        "SELECT archived_at FROM application WHERE application_id = ?",
        (application["application_id"],),
    ).fetchone()["archived_at"]
    conn.close()
    assert archived_at is None


def test_cancel_link_on_delete_confirm_returns_to_detail(client, application):
    body = client.get(
        f"/applications/{application['application_id']}/status/"
        f"{application['applied_history_id']}/delete"
    ).data.decode()

    assert 'id="cancel-status-delete"' in body
    assert (
        f'href="/applications/{application["application_id"]}">Cancel' in body
    )
