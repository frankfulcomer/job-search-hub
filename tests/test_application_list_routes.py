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
    return client.post("/applications/new", data=form)


def _table_html(client):
    # Drain any pending flash message first so its text can't be mistaken
    # for table content by a naive substring check.
    client.get("/applications")
    response = client.get("/applications")
    return response.data.decode()


def test_get_applications_list_returns_200(client):
    response = client.get("/applications")

    assert response.status_code == 200


def test_empty_state_shown_when_no_applications(client):
    response = client.get("/applications")

    assert b'id="applications-empty-state"' in response.data
    assert b'id="applications-table"' not in response.data


def test_table_shown_and_empty_state_hidden_once_applications_exist(client):
    _post_application(client)

    body = _table_html(client)

    assert 'id="applications-table"' in body
    assert 'id="applications-empty-state"' not in body


def test_list_displays_created_application_fields(client):
    _post_application(
        client,
        company_name="Acme Corp",
        job_title="Staff Engineer",
        source_name="Referral",
        job_location_city="Austin",
        job_location_state_province="TX",
        job_location_country="USA",
    )

    body = _table_html(client)

    assert "Acme Corp" in body
    assert "Staff Engineer" in body
    assert "Referral" in body
    assert "APPLIED" in body
    assert "Austin, TX, USA" in body


def test_missing_optional_job_location_renders_placeholder_not_blank(client):
    _post_application(client)

    body = _table_html(client)
    row_start = body.index('id="application-row-')
    row_html = body[row_start : row_start + 800]

    assert "—" in row_html


def test_default_order_is_application_date_descending(client):
    _post_application(
        client,
        company_name="Older Co",
        application_date="2026-09-01",
        initial_status_effective_at="2026-09-01T09:00",
    )
    _post_application(client, company_name="Newer Co", application_date="2026-09-20")

    body = _table_html(client)
    table_html = body[body.index('id="applications-table"') :]

    assert table_html.index("Newer Co") < table_html.index("Older Co")


def test_sort_by_company_ascending_changes_order(client):
    _post_application(client, company_name="Zeta Corp")
    _post_application(client, company_name="Alpha Corp")

    response = client.get("/applications?sort=company&dir=asc")
    body = response.data.decode()
    table_html = body[body.index('id="applications-table"') :]

    assert table_html.index("Alpha Corp") < table_html.index("Zeta Corp")
    assert 'aria-sort="ascending"' in body
    assert 'id="sort-company"' in body


def test_pagination_controls_hidden_for_single_page(client):
    _post_application(client)

    body = _table_html(client)

    assert 'id="pagination"' not in body


def test_pagination_controls_shown_for_multiple_pages(client, db_path):
    connection = db.connect(db_path)
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.execute("INSERT INTO source (name) VALUES ('Job Board')")
    applied_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'APPLIED'"
    ).fetchone()["status_id"]
    for i in range(26):
        cursor = connection.execute(
            "INSERT INTO application "
            "(company_id, source_id, job_title, application_date) "
            "VALUES (1, 1, ?, '2026-09-20')",
            (f"Role {i}",),
        )
        connection.execute(
            "INSERT INTO application_status_history "
            "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
            (cursor.lastrowid, applied_id, f"2026-09-20T{i % 24:02d}:00:00.000Z"),
        )
    connection.commit()
    connection.close()

    page1 = client.get("/applications")
    assert b'id="pagination"' in page1.data
    assert b"Page 1 of 2" in page1.data
    assert b'id="page-next"' in page1.data
    assert b'id="page-prev"' not in page1.data

    page2 = client.get("/applications?page=2")
    assert b"Page 2 of 2" in page2.data
    assert b'id="page-prev"' in page2.data
    assert b'id="page-next"' not in page2.data


def test_company_name_is_escaped_in_list(client):
    _post_application(client, company_name='<script>alert(1)</script>')

    body = _table_html(client)

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_create_application_redirects_to_list_page(client):
    response = _post_application(client, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "/applications"


def test_invalid_sort_and_page_query_params_do_not_error(client):
    _post_application(client)

    response = client.get("/applications?sort=nonsense&dir=nonsense&page=nonsense")

    assert response.status_code == 200
    assert b'id="applications-table"' in response.data
