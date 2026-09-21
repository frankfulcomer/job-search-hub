from datetime import date

import pytest

from job_hub import create_app, db


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


def _form(**overrides):
    form = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date.today().isoformat(),
        "source_name": "Job Board",
    }
    form.update(overrides)
    return form


def test_post_duplicate_by_external_job_id_shows_warning_and_does_not_save(client):
    client.post(
        "/applications/new",
        data=_form(external_job_id="REQ-1"),
        follow_redirects=True,
    )

    response = client.post(
        "/applications/new",
        data=_form(job_title="A Different Title", external_job_id="req-1"),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="duplicate-warning"' in body
    assert b"Created application" not in response.data

    list_body = client.get("/applications").data.decode()
    assert list_body.count("application-row-") == 1


def test_post_duplicate_by_company_and_job_title_shows_warning(client):
    client.post("/applications/new", data=_form())

    response = client.post("/applications/new", data=_form())
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="duplicate-warning"' in body


def test_post_non_duplicate_saves_without_warning(client):
    response = client.post(
        "/applications/new", data=_form(), follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Created application" in response.data
    assert b'id="duplicate-warning"' not in response.data


def test_warning_lists_the_matching_application(client):
    first_resp = client.post(
        "/applications/new", data=_form(external_job_id="REQ-1"), follow_redirects=True
    )
    assert b"Created application" in first_resp.data

    response = client.post(
        "/applications/new", data=_form(external_job_id="REQ-1")
    )
    body = response.data.decode()

    assert 'id="duplicate-match-1"' in body
    assert "Engineer at Acme Corp" in body


def test_warning_match_link_targets_the_existing_application_detail_page(client):
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))

    response = client.post(
        "/applications/new", data=_form(external_job_id="REQ-1")
    )
    body = response.data.decode()

    assert 'href="/applications/1"' in body
    assert 'target="_blank"' in body
    assert 'rel="noopener"' in body


def test_warning_preserves_entered_form_values(client):
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))

    response = client.post(
        "/applications/new",
        data=_form(
            job_title="Senior Engineer",
            external_job_id="REQ-1",
            notes="Some notes I already typed",
        ),
    )
    body = response.data.decode()

    assert 'value="Senior Engineer"' in body
    assert "Some notes I already typed" in body


def test_confirm_duplicate_checkbox_present_only_when_warning_shown(client):
    no_warning_body = client.get("/applications/new").data.decode()
    assert 'id="confirm_duplicate"' not in no_warning_body

    client.post("/applications/new", data=_form(external_job_id="REQ-1"))
    warning_response = client.post(
        "/applications/new", data=_form(external_job_id="REQ-1")
    )
    assert 'id="confirm_duplicate"' in warning_response.data.decode()


def test_post_with_confirm_duplicate_saves_anyway(client):
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))

    response = client.post(
        "/applications/new",
        data=_form(external_job_id="REQ-1", confirm_duplicate="1"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Created application" in response.data

    list_body = client.get("/applications").data.decode()
    assert list_body.count("application-row-") == 2


def test_archived_match_is_labeled_in_the_warning(client, db_path):
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))
    client.post("/applications/1/archive")

    response = client.post(
        "/applications/new", data=_form(external_job_id="REQ-1")
    )
    body = response.data.decode()

    assert "(archived)" in body


def test_cancel_link_present_on_fresh_create_form(client):
    body = client.get("/applications/new").data.decode()

    assert 'id="cancel-new-application"' in body
    assert 'href="/applications">Cancel' in body


def test_cancel_link_present_in_duplicate_warning_state(client):
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))

    response = client.post(
        "/applications/new", data=_form(external_job_id="REQ-1")
    )
    body = response.data.decode()

    assert 'id="duplicate-warning"' in body
    assert 'id="cancel-new-application"' in body
    assert 'href="/applications">Cancel' in body


def test_following_cancel_link_does_not_persist_the_abandoned_application(client):
    # The "duplicate" here stands in for any half-entered form; the point is
    # that abandoning the form (a GET, never a POST to /applications/new)
    # can never itself create an application, matching FR-002's "the user
    # shall be able to ... cancel the new application ... without changing
    # persisted data" - trivially true structurally, since GET never calls
    # create_application, but verified end-to-end here regardless.
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))
    client.post("/applications/new", data=_form(external_job_id="REQ-1"))

    before = client.get("/applications").data.decode().count("application-row-")

    client.get("/applications")  # following the Cancel link

    after = client.get("/applications").data.decode().count("application-row-")
    assert before == after == 1


def test_editing_an_application_does_not_trigger_duplicate_detection(client):
    client.post("/applications/new", data=_form(), follow_redirects=True)
    client.post(
        "/applications/new",
        data=_form(company_name="Globex", job_title="Analyst"),
        follow_redirects=True,
    )

    edit_form = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date.today().isoformat(),
        "source_name": "Job Board",
    }
    response = client.post(
        "/applications/2/edit", data=edit_form, follow_redirects=True
    )

    assert response.status_code == 200
    assert b'id="duplicate-warning"' not in response.data
