from datetime import date, datetime, timedelta, timezone

import pytest

from job_hub import create_app, db
from job_hub.applications import create_application

NOW = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)


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


def _create_application(db_path, **overrides):
    fields = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date(2026, 9, 18),
        "source_name": "Job Board",
        "initial_status_effective_at": datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc),
        "now": NOW,
    }
    fields.update(overrides)
    conn = db.connect(db_path)
    result = create_application(conn, **fields)
    conn.close()
    return result.application_id


@pytest.fixture
def application_id(db_path):
    return _create_application(db_path)


# --- archive ----------------------------------------------------------


def test_get_archive_confirm_returns_200(client, application_id):
    response = client.get(f"/applications/{application_id}/archive")

    assert response.status_code == 200
    assert b'id="archive-confirm-form"' in response.data


def test_get_archive_confirm_for_nonexistent_application_returns_404(client):
    response = client.get("/applications/999999/archive")

    assert response.status_code == 404


def test_detail_page_links_to_archive_for_active_application(client, application_id):
    body = client.get(f"/applications/{application_id}").data.decode()

    assert f'href="/applications/{application_id}/archive"' in body
    assert 'id="archive-application-link"' in body
    assert 'id="restore-application-link"' not in body


def test_post_archive_redirects_and_flashes(client, application_id):
    response = client.post(
        f"/applications/{application_id}/archive", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Archived application" in response.data
    assert b'id="detail-archived-notice"' in response.data


def test_post_archive_for_nonexistent_application_returns_404(client):
    response = client.post("/applications/999999/archive")

    assert response.status_code == 404


def test_post_archive_removes_application_from_default_list(client, application_id):
    client.post(f"/applications/{application_id}/archive")

    body = client.get("/applications").data.decode()
    assert f'id="application-row-{application_id}"' not in body


def test_post_archive_records_archived_at_close_to_the_request_time(
    client, application_id, db_path
):
    # `now` isn't injectable through an HTTP request, so this checks the
    # persisted value falls within a window around the real request rather
    # than an exact value (unlike the service-level test, which injects a
    # fixed `now`).
    before = datetime.now(timezone.utc)
    client.post(f"/applications/{application_id}/archive")
    after = datetime.now(timezone.utc)

    conn = db.connect(db_path)
    archived_at_str = conn.execute(
        "SELECT archived_at FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()["archived_at"]
    conn.close()

    archived_at = datetime.strptime(
        archived_at_str, "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    # ADR-0001 guarantees millisecond persistence precision, not exact
    # microsecond precision: archive_application formats archived_at via
    # _format_timestamp, which truncates (rather than rounds) to the
    # millisecond via `value.microsecond // 1000`, so the persisted value
    # can legitimately land up to ~1ms below a `before` bound captured with
    # Python's full microsecond precision, even though the real write
    # happened after `before`. Comparing against a tolerance matching the
    # documented storage precision - rather than assuming precision
    # persistence doesn't guarantee - avoids a genuine, reproducible flake
    # without weakening what the test actually verifies (that archived_at
    # reflects the real request time, not a stale or mistimed value).
    tolerance = timedelta(milliseconds=1)
    assert before - tolerance <= archived_at <= after + tolerance


def test_post_archive_does_not_change_status_history(client, application_id):
    before = client.get(f"/applications/{application_id}").data.decode()
    assert 'id="detail-current-status">APPLIED<' in before

    client.post(f"/applications/{application_id}/archive")

    after = client.get(f"/applications/{application_id}").data.decode()
    assert 'id="detail-current-status">APPLIED<' in after


def test_cancel_link_on_archive_confirm_returns_to_detail(client, application_id):
    body = client.get(f"/applications/{application_id}/archive").data.decode()

    assert 'id="cancel-archive"' in body
    assert f'href="/applications/{application_id}">Cancel' in body


def test_get_on_archive_does_not_archive(client, application_id):
    client.get(f"/applications/{application_id}/archive")

    body = client.get("/applications").data.decode()
    assert f'id="application-row-{application_id}"' in body


# --- restore ------------------------------------------------------------


def test_get_on_restore_route_is_not_allowed(client, application_id):
    client.post(f"/applications/{application_id}/archive")

    response = client.get(f"/applications/{application_id}/restore")

    assert response.status_code == 405


def test_post_restore_redirects_and_flashes(client, application_id):
    client.post(f"/applications/{application_id}/archive")

    response = client.post(
        f"/applications/{application_id}/restore", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Restored application" in response.data
    assert b'id="detail-archived-notice"' not in response.data


def test_post_restore_for_nonexistent_application_returns_404(client):
    response = client.post("/applications/999999/restore")

    assert response.status_code == 404


def test_post_restore_returns_application_to_default_list(client, application_id):
    client.post(f"/applications/{application_id}/archive")
    client.post(f"/applications/{application_id}/restore")

    body = client.get("/applications").data.decode()
    assert f'id="application-row-{application_id}"' in body


def test_detail_page_shows_restore_link_for_archived_application(
    client, application_id
):
    client.post(f"/applications/{application_id}/archive")

    body = client.get(f"/applications/{application_id}").data.decode()
    assert 'id="restore-application-link"' in body
    assert 'id="archive-application-link"' not in body


# --- minimal record-state list visibility --------------------------------


def test_default_list_shows_only_active_applications(client, db_path):
    active_id = _create_application(db_path, company_name="Active Co")
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    body = client.get("/applications").data.decode()

    assert f'id="application-row-{active_id}"' in body
    assert f'id="application-row-{archived_id}"' not in body


def test_archived_state_shows_only_archived_applications(client, db_path):
    active_id = _create_application(db_path, company_name="Active Co")
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    body = client.get("/applications?state=archived").data.decode()

    assert f'id="application-row-{archived_id}"' in body
    assert f'id="application-row-{active_id}"' not in body


def test_all_state_shows_both_and_visually_distinguishes_archived(client, db_path):
    active_id = _create_application(db_path, company_name="Active Co")
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    body = client.get("/applications?state=all").data.decode()

    assert f'id="application-row-{active_id}"' in body
    assert f'id="application-row-{archived_id}"' in body
    archived_row_start = body.index(f'id="application-row-{archived_id}"')
    archived_row_end = body.index("</tr>", archived_row_start)
    assert 'class="archived-row"' in body[archived_row_start:archived_row_end]

    active_row_start = body.index(f'id="application-row-{active_id}"')
    active_row_end = body.index("</tr>", active_row_start)
    assert 'class="archived-row"' not in body[active_row_start:active_row_end]


def test_record_state_links_present_on_list_page(client, application_id):
    body = client.get("/applications").data.decode()

    assert 'id="record-state-active"' in body
    assert 'id="record-state-archived"' in body
    assert 'id="record-state-all"' in body


def test_active_state_list_has_no_actions_column(client, application_id):
    body = client.get("/applications").data.decode()

    assert "Actions" not in body


def test_archived_state_list_shows_inline_restore_action(client, db_path):
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    body = client.get("/applications?state=archived").data.decode()

    assert f'id="restore-application-{archived_id}"' in body


def test_all_state_list_shows_restore_only_for_archived_rows(client, db_path):
    active_id = _create_application(db_path, company_name="Active Co")
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    body = client.get("/applications?state=all").data.decode()

    assert f'id="restore-application-{archived_id}"' in body
    assert f'id="restore-application-{active_id}"' not in body


def test_post_restore_from_list_rendered_form_returns_application_to_active(
    client, db_path
):
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    response = client.post(
        f"/applications/{archived_id}/restore", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Restored application" in response.data
    body = client.get("/applications").data.decode()
    assert f'id="application-row-{archived_id}"' in body


def test_empty_archived_state_shows_no_results_message(client, application_id):
    body = client.get("/applications?state=archived").data.decode()

    assert 'id="applications-empty-state"' in body
    assert "No archived applications." in body


def test_unrecognized_state_falls_back_to_active(client, db_path):
    active_id = _create_application(db_path, company_name="Active Co")
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    body = client.get("/applications?state=bogus").data.decode()

    assert f'id="application-row-{active_id}"' in body
    assert f'id="application-row-{archived_id}"' not in body


def test_out_of_range_page_for_a_record_state_clamps_instead_of_erroring(
    client, db_path
):
    active_id = _create_application(db_path, company_name="Active Co")
    archived_id = _create_application(db_path, company_name="Archived Co")
    client.post(f"/applications/{archived_id}/archive")

    # Only one archived application exists (one page), but request page 5.
    response = client.get("/applications?state=archived&page=5")
    body = response.data.decode()

    assert response.status_code == 200
    assert f'id="application-row-{archived_id}"' in body
    assert f'id="application-row-{active_id}"' not in body
