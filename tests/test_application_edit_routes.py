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


def _post_application(client, **overrides):
    form = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date.today().isoformat(),
        "source_name": "Job Board",
    }
    form.update(overrides)
    client.post("/applications/new", data=form)


def _application_id(db_path):
    conn = db.connect(db_path)
    row = conn.execute(
        "SELECT application_id FROM application ORDER BY application_id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["application_id"]


def _edit_form(**overrides):
    form = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date.today().isoformat(),
        "source_name": "Job Board",
    }
    form.update(overrides)
    return form


def test_get_edit_form_returns_200_prefilled(client, db_path):
    _post_application(client, job_title="Staff Engineer")
    application_id = _application_id(db_path)

    response = client.get(f"/applications/{application_id}/edit")
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="edit-application-form"' in body
    assert 'value="Staff Engineer"' in body
    assert "None" not in body


def test_get_edit_form_for_nonexistent_id_returns_404(client):
    response = client.get("/applications/999999/edit")

    assert response.status_code == 404


def test_detail_page_links_to_edit_page(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert f'href="/applications/{application_id}/edit"' in body


def test_edit_page_has_cancel_link_to_detail(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}/edit").data.decode()

    assert 'id="cancel-edit"' in body
    assert f'href="/applications/{application_id}">Cancel' in body


def test_post_valid_edit_updates_and_redirects_to_detail(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(job_title="Updated Title"),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/applications/{application_id}"

    conn = db.connect(db_path)
    row = conn.execute(
        "SELECT job_title FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    assert row["job_title"] == "Updated Title"
    conn.close()


def test_post_edit_preserves_status_history(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit", data=_edit_form(job_title="Changed")
    )

    conn = db.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM application_status_history WHERE application_id = ?",
        (application_id,),
    ).fetchone()["n"]
    conn.close()
    assert count == 1


def test_post_edit_validation_failure_shows_error_and_preserves_input(
    client, db_path
):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit", data=_edit_form(job_title="")
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert 'value="Acme Corp"' in body


def test_post_edit_shared_headquarters_change_shows_confirmation_without_persisting(
    client, db_path
):
    _post_application(
        client,
        company_hq_city="Austin",
        company_hq_state_province="TX",
        company_hq_country="USA",
    )
    application_id = _application_id(db_path)
    _post_application(client, job_title="Engineer 2")  # shares the same company

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            company_hq_city="Chicago",
            company_hq_state_province="IL",
            company_hq_country="USA",
        ),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="shared-headquarters-warning"' in body
    assert 'id="confirm_shared_headquarters_change"' in body

    conn = db.connect(db_path)
    hq_city = conn.execute(
        "SELECT l.city FROM location l "
        "JOIN company c ON c.hq_location_id = l.location_id "
        "JOIN application a ON a.company_id = c.company_id "
        "WHERE a.application_id = ?",
        (application_id,),
    ).fetchone()["city"]
    conn.close()
    assert hq_city == "Austin"


def test_reassignment_does_not_leak_previous_companys_headquarters_to_shared_target(
    client, db_path
):
    _post_application(
        client,
        company_name="Company A",
        company_hq_city="Austin",
        company_hq_state_province="TX",
        company_hq_country="USA",
    )
    application_id = _application_id(db_path)
    _post_application(
        client,
        company_name="Company B",
        job_title="Engineer 2",
        company_hq_city="Chicago",
        company_hq_state_province="IL",
        company_hq_country="USA",
    )
    _post_application(client, company_name="Company B", job_title="Engineer 3")

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            company_name="Company B",
            company_hq_city="Austin",
            company_hq_state_province="TX",
            company_hq_country="USA",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert 'id="shared-headquarters-warning"' not in response.data.decode()

    conn = db.connect(db_path)
    hq_city = conn.execute(
        "SELECT l.city FROM location l JOIN company c ON c.hq_location_id = l.location_id "
        "WHERE c.name = 'Company B'"
    ).fetchone()["city"]
    conn.close()
    assert hq_city == "Chicago"


def test_reassignment_to_new_company_does_not_silently_apply_stale_headquarters(
    client, db_path
):
    _post_application(
        client,
        company_name="Company A",
        company_hq_city="Austin",
        company_hq_state_province="TX",
        company_hq_country="USA",
    )
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            company_name="Company C (brand new)",
            company_hq_city="Austin",
            company_hq_state_province="TX",
            company_hq_country="USA",
        ),
    )

    assert response.status_code == 302

    conn = db.connect(db_path)
    row = conn.execute(
        "SELECT hq_location_id FROM company WHERE name = 'Company C (brand new)'"
    ).fetchone()
    conn.close()
    assert row["hq_location_id"] is None


def test_headquarters_settable_in_followup_edit_after_reassignment(client, db_path):
    _post_application(client, company_name="Company A")
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(company_name="Company C (brand new)"),
    )
    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            company_name="Company C (brand new)",
            company_hq_city="Denver",
            company_hq_state_province="CO",
            company_hq_country="USA",
        ),
    )

    conn = db.connect(db_path)
    hq_city = conn.execute(
        "SELECT l.city FROM location l JOIN company c ON c.hq_location_id = l.location_id "
        "WHERE c.name = 'Company C (brand new)'"
    ).fetchone()["city"]
    conn.close()
    assert hq_city == "Denver"


def test_reassignment_shows_informational_flash_message(client, db_path):
    _post_application(client, company_name="Company A")
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(company_name="Company D (new)"),
        follow_redirects=True,
    )

    assert b"Company changed" in response.data


def test_post_edit_confirmed_shared_headquarters_change_persists_for_both_applications(
    client, db_path
):
    _post_application(
        client,
        company_hq_city="Austin",
        company_hq_state_province="TX",
        company_hq_country="USA",
    )
    application_id = _application_id(db_path)
    _post_application(client, job_title="Engineer 2")
    other_application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            company_hq_city="Chicago",
            company_hq_state_province="IL",
            company_hq_country="USA",
            confirm_shared_headquarters_change="1",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302

    conn = db.connect(db_path)
    for app_id in (application_id, other_application_id):
        hq_city = conn.execute(
            "SELECT l.city FROM location l "
            "JOIN company c ON c.hq_location_id = l.location_id "
            "JOIN application a ON a.company_id = c.company_id "
            "WHERE a.application_id = ?",
            (app_id,),
        ).fetchone()["city"]
        assert hq_city == "Chicago"
    conn.close()


def test_post_edit_compensation_min_exceeds_max_shows_specific_validation_error(
    client, db_path
):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            compensation_min="200000",
            compensation_max="100000",
            compensation_basis="ANNUAL",
        ),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert "compensation_max" in body
    idx = body.index('id="compensation_min"')
    assert 'aria-invalid="true"' in body[idx : idx + 200]


def test_post_edit_compensation_min_exceeds_max_does_not_change_persisted_value(
    client, db_path
):
    _post_application(
        client,
        compensation_min="50000",
        compensation_max="60000",
        compensation_basis="ANNUAL",
    )
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            compensation_min="200000",
            compensation_max="100000",
            compensation_basis="ANNUAL",
        ),
    )

    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT compensation_min, compensation_max FROM application "
        "WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    connection.close()
    assert row["compensation_min"] == 50000
    assert row["compensation_max"] == 60000


def test_post_edit_for_nonexistent_id_returns_404(client):
    response = client.post("/applications/999999/edit", data=_edit_form())

    assert response.status_code == 404


# --- FR-011: job URL syntactic validation -----------------------------------


def test_post_edit_invalid_job_url_shows_validation_error_and_marks_field(
    client, db_path
):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(job_url="not a url"),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    idx = body.index('id="job_url"')
    assert 'aria-invalid="true"' in body[idx : idx + 120]


def test_post_edit_invalid_job_url_does_not_change_persisted_value(
    client, db_path
):
    _post_application(client, job_url="https://example.com/original")
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(job_url="javascript:alert(1)"),
    )

    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT job_url FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    connection.close()
    assert row["job_url"] == "https://example.com/original"


def test_post_edit_valid_job_url_is_saved(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(job_url="https://example.com/updated"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT job_url FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    connection.close()
    assert row["job_url"] == "https://example.com/updated"


def test_post_edit_can_clear_job_url_back_to_blank(client, db_path):
    _post_application(client, job_url="https://example.com/original")
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(job_url=""),
    )

    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT job_url FROM application WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    connection.close()
    assert row["job_url"] is None


# --- FR-011: compensation basis required when compensation is provided -----


def test_post_edit_compensation_without_basis_shows_specific_validation_error(
    client, db_path
):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(compensation_min="100000"),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    idx = body.index('id="compensation_basis"')
    assert 'aria-invalid="true"' in body[idx : idx + 200]


def test_post_edit_compensation_without_basis_does_not_change_persisted_value(
    client, db_path
):
    _post_application(
        client,
        compensation_min="50000",
        compensation_max="60000",
        compensation_basis="ANNUAL",
    )
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(compensation_min="100000"),
    )

    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT compensation_min, compensation_basis FROM application "
        "WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    connection.close()
    assert row["compensation_min"] == 50000
    assert row["compensation_basis"] == "ANNUAL"


def test_post_edit_compensation_with_basis_succeeds(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(
            compensation_min="100000",
            compensation_max="150000",
            compensation_basis="ANNUAL",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    connection = db.connect(db_path)
    row = connection.execute(
        "SELECT compensation_min, compensation_basis FROM application "
        "WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    connection.close()
    assert row["compensation_min"] == 100000
    assert row["compensation_basis"] == "ANNUAL"


# --- FR-010: reference-data selection ----------------------------------------


def test_edit_form_renders_datalists(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}/edit").data.decode()

    assert 'id="company-name-options"' in body
    assert 'id="source-name-options"' in body
    assert 'id="location-city-options"' in body
    assert 'id="location-state-province-options"' in body
    assert 'id="location-country-options"' in body


def test_edit_form_lists_existing_reference_values_from_other_applications(
    client, db_path
):
    _post_application(
        client,
        company_name="Acme Corp",
        source_name="LinkedIn",
        job_location_city="Austin",
        job_location_state_province="TX",
        job_location_country="USA",
    )
    _post_application(client, company_name="Other Co", job_title="Engineer 2")
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}/edit").data.decode()

    assert '<option value="Acme Corp">' in body
    assert '<option value="LinkedIn">' in body
    assert '<option value="Austin">' in body


def test_edit_form_inputs_reference_the_datalists(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}/edit").data.decode()

    idx = body.index('id="company_name"')
    assert 'list="company-name-options"' in body[idx : idx + 200]

    idx = body.index('id="source_name"')
    assert 'list="source-name-options"' in body[idx : idx + 200]

    idx = body.index('id="job_location_city"')
    assert 'list="location-city-options"' in body[idx : idx + 200]

    idx = body.index('id="company_hq_city"')
    assert 'list="location-city-options"' in body[idx : idx + 200]


def test_post_edit_selecting_existing_company_by_exact_name_reuses_it(
    client, db_path
):
    _post_application(client, company_name="Acme Corp")
    _post_application(client, company_name="Other Co", job_title="Engineer 2")
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(company_name="Other Co"),
    )

    conn = db.connect(db_path)
    count = conn.execute("SELECT COUNT(*) AS n FROM company").fetchone()["n"]
    conn.close()
    assert count == 2


def test_post_edit_new_company_name_not_in_datalist_still_creates_it(
    client, db_path
):
    _post_application(client, company_name="Acme Corp")
    application_id = _application_id(db_path)

    client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(company_name="Brand New Co"),
    )

    conn = db.connect(db_path)
    names = {row["name"] for row in conn.execute("SELECT name FROM company").fetchall()}
    conn.close()
    assert names == {"Acme Corp", "Brand New Co"}


def test_datalist_options_still_present_on_edit_validation_error_redisplay(
    client, db_path
):
    _post_application(client, company_name="Acme Corp")
    _post_application(client, company_name="Other Co", job_title="Engineer 2")
    application_id = _application_id(db_path)

    response = client.post(
        f"/applications/{application_id}/edit",
        data=_edit_form(job_title=""),
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert '<option value="Other Co">' in body
