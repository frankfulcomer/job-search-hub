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


# --- FR-011: job URL syntactic validation -----------------------------------


def test_post_invalid_job_url_shows_validation_error_and_marks_field(client):
    response = client.post(
        "/applications/new", data=_valid_form(job_url="not a url")
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    idx = body.index('id="job_url"')
    assert 'aria-invalid="true"' in body[idx : idx + 120]


def test_post_invalid_job_url_preserves_other_entered_values(client):
    response = client.post(
        "/applications/new",
        data=_valid_form(job_url="javascript:alert(1)", job_title="Staff Engineer"),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'value="Staff Engineer"' in body
    assert 'value="javascript:alert(1)"' in body


def test_post_valid_job_url_is_saved(client, db_path):
    client.post(
        "/applications/new", data=_valid_form(job_url="https://example.com/job/1")
    )

    connection = db.connect(db_path)
    row = connection.execute("SELECT job_url FROM application").fetchone()
    assert row["job_url"] == "https://example.com/job/1"
    connection.close()


def test_post_blank_job_url_remains_optional(client, db_path):
    response = client.post("/applications/new", data=_valid_form(job_url=""))

    assert response.status_code == 302
    connection = db.connect(db_path)
    row = connection.execute("SELECT job_url FROM application").fetchone()
    assert row["job_url"] is None
    connection.close()


# --- FR-011: compensation basis required when compensation is provided -----


def test_post_compensation_without_basis_shows_specific_validation_error(client):
    response = client.post(
        "/applications/new", data=_valid_form(compensation_min="100000")
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert "compensation_basis" in body
    idx = body.index('id="compensation_basis"')
    assert 'aria-invalid="true"' in body[idx : idx + 200]


def test_post_compensation_without_basis_does_not_create_application(
    client, db_path
):
    client.post("/applications/new", data=_valid_form(compensation_min="100000"))

    connection = db.connect(db_path)
    count = connection.execute("SELECT COUNT(*) AS n FROM application").fetchone()["n"]
    connection.close()
    assert count == 0


def test_post_compensation_with_basis_succeeds(client, db_path):
    response = client.post(
        "/applications/new",
        data=_valid_form(
            compensation_min="100000",
            compensation_max="150000",
            compensation_basis="ANNUAL",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT compensation_min, compensation_basis FROM application"
    ).fetchone()
    connection.close()
    assert row["compensation_min"] == 100000
    assert row["compensation_basis"] == "ANNUAL"


# --- FR-010: reference-data selection ---------------------------------------


def test_new_application_form_has_no_datalist_options_when_none_exist(client):
    body = client.get("/applications/new").data.decode()

    assert 'id="company-name-options"' in body
    assert 'id="source-name-options"' in body
    assert 'id="location-city-options"' in body
    assert 'id="location-state-province-options"' in body
    assert 'id="location-country-options"' in body

    datalists_start = body.index('id="company-name-options"')
    datalists_end = body.index('id="create-application-form"')
    datalists_region = body[datalists_start:datalists_end]
    assert '<option value=' not in datalists_region


def test_new_application_form_lists_existing_reference_values(client, db_path):
    client.post(
        "/applications/new",
        data=_valid_form(
            company_name="Acme Corp",
            source_name="LinkedIn",
            job_location_city="Austin",
            job_location_state_province="TX",
            job_location_country="USA",
        ),
    )

    body = client.get("/applications/new").data.decode()

    assert '<option value="Acme Corp">' in body
    assert '<option value="LinkedIn">' in body
    assert '<option value="Austin">' in body
    assert '<option value="TX">' in body
    assert '<option value="USA">' in body


def test_new_application_form_inputs_reference_the_datalists(client):
    body = client.get("/applications/new").data.decode()

    idx = body.index('id="company_name"')
    assert 'list="company-name-options"' in body[idx : idx + 200]

    idx = body.index('id="source_name"')
    assert 'list="source-name-options"' in body[idx : idx + 200]

    idx = body.index('id="job_location_city"')
    assert 'list="location-city-options"' in body[idx : idx + 200]

    idx = body.index('id="company_hq_city"')
    assert 'list="location-city-options"' in body[idx : idx + 200]


def test_post_selecting_existing_company_by_exact_name_reuses_it(client, db_path):
    client.post("/applications/new", data=_valid_form(company_name="Acme Corp"))
    client.post(
        "/applications/new",
        data=_valid_form(company_name="Acme Corp", job_title="Manager"),
    )

    connection = db.connect(db_path)
    count = connection.execute("SELECT COUNT(*) AS n FROM company").fetchone()["n"]
    connection.close()
    assert count == 1


def test_post_new_company_name_not_in_datalist_still_creates_it(client, db_path):
    client.post("/applications/new", data=_valid_form(company_name="Existing Co"))
    client.post(
        "/applications/new",
        data=_valid_form(company_name="Brand New Co", job_title="Analyst"),
    )

    connection = db.connect(db_path)
    names = {
        row["name"]
        for row in connection.execute("SELECT name FROM company").fetchall()
    }
    connection.close()
    assert names == {"Existing Co", "Brand New Co"}


def test_post_selecting_existing_location_by_exact_components_reuses_it(
    client, db_path
):
    client.post(
        "/applications/new",
        data=_valid_form(
            job_location_city="Austin",
            job_location_state_province="TX",
            job_location_country="USA",
        ),
    )
    client.post(
        "/applications/new",
        data=_valid_form(
            job_title="Manager",
            job_location_city="Austin",
            job_location_state_province="TX",
            job_location_country="USA",
        ),
    )

    connection = db.connect(db_path)
    count = connection.execute("SELECT COUNT(*) AS n FROM location").fetchone()["n"]
    connection.close()
    assert count == 1


def test_datalist_options_still_present_on_validation_error_redisplay(
    client, db_path
):
    client.post("/applications/new", data=_valid_form(company_name="Acme Corp"))

    response = client.post(
        "/applications/new", data=_valid_form(company_name="")
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert '<option value="Acme Corp">' in body


def test_datalist_options_still_present_on_duplicate_warning_redisplay(
    client, db_path
):
    client.post(
        "/applications/new",
        data=_valid_form(company_name="Acme Corp", external_job_id="REQ-1"),
        follow_redirects=True,
    )

    response = client.post(
        "/applications/new",
        data=_valid_form(company_name="Acme Corp", external_job_id="REQ-1"),
    )
    body = response.data.decode()

    assert 'id="duplicate-warning"' in body
    assert '<option value="Acme Corp">' in body
