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


def _valid_form(**overrides):
    form = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date.today().isoformat(),
        "source_name": "Job Board",
    }
    form.update(overrides)
    return form


def test_home_page_links_to_new_application_form(client):
    response = client.get("/")

    assert b'href="/applications/new"' in response.data


def test_get_new_application_form_renders(client):
    response = client.get("/applications/new")

    assert response.status_code == 200
    assert b'id="create-application-form"' in response.data
    assert b"APPLIED" in response.data


def test_post_valid_application_creates_and_redirects(client, db_path):
    response = client.post(
        "/applications/new", data=_valid_form(), follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Created application for Engineer at Acme Corp" in response.data

    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT job_title FROM application"
    ).fetchone()
    assert row["job_title"] == "Engineer"
    connection.close()


def test_post_missing_job_title_rerenders_form_with_error_and_preserves_input(client):
    response = client.post(
        "/applications/new", data=_valid_form(job_title=""), follow_redirects=False
    )

    assert response.status_code == 200
    assert b'id="form-error"' in response.data
    assert b'value="Acme Corp"' in response.data


def test_post_missing_effective_at_for_non_today_date_shows_validation_error(client):
    response = client.post(
        "/applications/new",
        data=_valid_form(application_date="2020-01-01"),
    )

    assert response.status_code == 200
    assert b"initial_status_effective_at" in response.data


def test_post_invalid_work_arrangement_shows_validation_error(client):
    response = client.post(
        "/applications/new",
        data=_valid_form(work_arrangement="FROM_THE_MOON"),
    )

    assert response.status_code == 200
    assert b'id="form-error"' in response.data


def test_post_invalid_date_format_shows_validation_error(client):
    response = client.post(
        "/applications/new",
        data=_valid_form(application_date="not-a-date"),
    )

    assert response.status_code == 200
    assert b'id="form-error"' in response.data


def test_post_reuses_existing_company_across_submissions(client, db_path):
    client.post("/applications/new", data=_valid_form())
    client.post(
        "/applications/new",
        data=_valid_form(company_name="  acme corp  ", job_title="Manager"),
    )

    connection = db.connect(db_path)
    companies = connection.execute("SELECT COUNT(*) AS n FROM company").fetchone()
    assert companies["n"] == 1
    connection.close()


def test_post_database_constraint_failure_shows_generic_error_not_a_crash(client):
    response = client.post(
        "/applications/new",
        data=_valid_form(
            compensation_min="200000",
            compensation_max="100000",
            compensation_basis="ANNUAL",
        ),
    )

    assert response.status_code == 200
    assert b'id="form-error"' in response.data


def test_post_non_finite_compensation_shows_validation_error(client, db_path):
    response = client.post(
        "/applications/new",
        data=_valid_form(compensation_min="nan", compensation_basis="ANNUAL"),
    )

    assert response.status_code == 200
    assert b'id="form-error"' in response.data

    connection = db.connect(db_path)
    count = connection.execute("SELECT COUNT(*) AS n FROM application").fetchone()
    assert count["n"] == 0
    connection.close()


def test_post_infinite_compensation_shows_validation_error(client, db_path):
    response = client.post(
        "/applications/new",
        data=_valid_form(
            compensation_min="100",
            compensation_max="inf",
            compensation_basis="ANNUAL",
        ),
    )

    assert response.status_code == 200
    assert b'id="form-error"' in response.data

    connection = db.connect(db_path)
    count = connection.execute("SELECT COUNT(*) AS n FROM application").fetchone()
    assert count["n"] == 0
    connection.close()


def test_validation_error_marks_the_failing_field_and_is_announced(client):
    response = client.post(
        "/applications/new", data=_valid_form(job_title="")
    )
    body = response.data.decode()

    assert 'role="alert"' in body
    assert 'id="job_title"' in body
    assert 'aria-invalid="true"' in body
    # Only the failing field should be marked invalid.
    assert body.count('aria-invalid="true"') == 1


def test_flash_messages_region_has_live_region_attributes(client):
    client.post("/applications/new", data=_valid_form())
    response = client.get("/")

    assert 'id="flash-messages" role="status" aria-live="polite"' in response.data.decode()


def test_post_optional_job_location_is_saved(client, db_path):
    client.post(
        "/applications/new",
        data=_valid_form(
            job_location_city="Austin",
            job_location_state_province="TX",
            job_location_country="USA",
        ),
    )

    connection = db.connect(db_path)
    location = connection.execute("SELECT city FROM location").fetchone()
    assert location["city"] == "Austin"
    connection.close()
