from datetime import date, datetime, timezone

import pytest

from job_hub import create_app, db
from job_hub.applications import create_application


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
def application_id(db_path):
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
    conn.close()
    return result.application_id


def _status_form(**overrides):
    form = {
        "status_name": "SCREENING",
        "effective_at": "2026-09-19T10:00",
    }
    form.update(overrides)
    return form


def test_get_status_form_returns_200(client, application_id):
    response = client.get(f"/applications/{application_id}/status")

    assert response.status_code == 200
    assert b'id="status-change-form"' in response.data


def test_get_status_form_for_nonexistent_id_returns_404(client):
    response = client.get("/applications/999999/status")

    assert response.status_code == 404


def test_get_status_form_has_no_status_preselected(client, application_id):
    body = client.get(f"/applications/{application_id}/status").data.decode()

    assert '<option value="" selected>' in body
    # None of the real status options should carry `selected`.
    assert 'value="APPLIED"\n                    selected' not in body
    assert 'value="SCREENING"\n                    selected' not in body


def test_get_status_form_shows_current_status(client, application_id):
    body = client.get(f"/applications/{application_id}/status").data.decode()

    assert 'id="status-change-current-status">APPLIED<' in body


def test_detail_page_links_to_status_change_page(client, application_id):
    body = client.get(f"/applications/{application_id}").data.decode()

    assert f'href="/applications/{application_id}/status"' in body


def test_post_valid_status_change_redirects_and_flashes(client, application_id):
    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Recorded status change to SCREENING" in response.data
    assert b'id="detail-current-status">SCREENING<' in response.data


def test_post_backdated_status_change_does_not_become_current(client, application_id):
    client.post(f"/applications/{application_id}/status", data=_status_form())

    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(status_name="ACCEPTED", effective_at="2026-09-18T12:00"),
        follow_redirects=False,
    )
    assert response.status_code == 302

    detail_body = client.get(f"/applications/{application_id}").data.decode()
    assert 'id="detail-current-status">SCREENING<' in detail_body
    assert "ACCEPTED" in detail_body


def test_post_missing_status_shows_error_and_preserves_effective_at(
    client, application_id
):
    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(status_name=""),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert 'aria-invalid="true"' in body
    assert 'value="2026-09-19T10:00"' in body


def test_post_missing_effective_at_shows_error(client, application_id):
    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(effective_at=""),
    )

    assert response.status_code == 200
    assert 'id="form-error"' in response.data.decode()


def test_post_future_effective_at_shows_error(client, application_id):
    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(effective_at="2030-01-01T00:00"),
    )

    assert response.status_code == 200
    assert 'id="form-error"' in response.data.decode()


def test_post_duplicate_effective_at_shows_generic_error(client, application_id):
    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(effective_at="2026-09-18T09:00"),  # collides with APPLIED
    )

    assert response.status_code == 200
    assert 'id="form-error"' in response.data.decode()


def test_post_reselecting_current_status_succeeds(client, application_id):
    response = client.post(
        f"/applications/{application_id}/status",
        data=_status_form(
            status_name="APPLIED",
            effective_at="2026-09-20T08:00",
            notes="Still applied, following up",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302
    detail_body = client.get(f"/applications/{application_id}").data.decode()
    assert 'id="detail-current-status">APPLIED<' in detail_body
    assert "Still applied, following up" in detail_body


def test_cancel_link_returns_to_detail(client, application_id):
    body = client.get(f"/applications/{application_id}/status").data.decode()

    assert 'id="cancel-status-change"' in body
    assert f'href="/applications/{application_id}">Cancel' in body


def test_post_does_not_alter_archived_at(client, application_id, db_path):
    client.post(f"/applications/{application_id}/status", data=_status_form())

    conn = db.connect(db_path)
    archived_at = conn.execute(
        "SELECT archived_at FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()["archived_at"]
    conn.close()
    assert archived_at is None


def test_post_for_nonexistent_id_returns_404(client):
    response = client.post("/applications/999999/status", data=_status_form())

    assert response.status_code == 404


def test_status_change_does_not_modify_other_application_fields(
    client, application_id, db_path
):
    before_body = client.get(f"/applications/{application_id}").data.decode()
    assert "Engineer" in before_body

    client.post(f"/applications/{application_id}/status", data=_status_form())

    after_body = client.get(f"/applications/{application_id}").data.decode()
    assert 'id="detail-job-title">Engineer<' in after_body
    assert 'id="detail-company">Acme Corp<' in after_body
