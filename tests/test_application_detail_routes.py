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


def test_get_detail_returns_200_with_expected_fields(client, db_path):
    _post_application(
        client,
        company_name="Acme Corp",
        job_title="Staff Engineer",
        source_name="Referral",
    )
    application_id = _application_id(db_path)

    response = client.get(f"/applications/{application_id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="detail-job-title">Staff Engineer<' in body
    assert 'id="detail-company">Acme Corp<' in body
    assert 'id="detail-source">Referral<' in body
    assert 'id="detail-current-status">APPLIED<' in body


def test_get_detail_for_nonexistent_id_returns_404(client):
    response = client.get("/applications/999999")

    assert response.status_code == 404


def test_get_detail_for_out_of_range_id_returns_404_not_500(client):
    response = client.get("/applications/999999999999999999999999999999")

    assert response.status_code == 404


def test_compensation_values_render_without_trailing_zero(client, db_path):
    _post_application(
        client,
        compensation_min="100000",
        compensation_max="150000",
        compensation_basis="ANNUAL",
    )
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert 'id="detail-compensation-min">100000<' in body
    assert 'id="detail-compensation-max">150000<' in body
    assert "100000.0" not in body
    assert "150000.0" not in body


def test_missing_optional_fields_render_placeholder_not_blank(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert 'id="detail-work-arrangement">—<' in body
    assert 'id="detail-employment-type">—<' in body
    assert 'id="detail-external-job-id">—<' in body
    assert 'id="detail-job-description">—<' in body
    assert 'id="detail-notes">—<' in body
    assert 'id="detail-company-hq">—<' in body
    assert 'id="detail-job-location">—<' in body


def test_compensation_fields_shown_only_when_present(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert 'id="detail-compensation-min"' not in body
    assert 'id="detail-compensation-max"' not in body
    assert 'id="detail-compensation-basis"' not in body

    _post_application(
        client,
        job_title="Engineer 2",
        compensation_min="100000",
        compensation_basis="ANNUAL",
    )
    application_id2 = _application_id(db_path)
    body2 = client.get(f"/applications/{application_id2}").data.decode()

    assert 'id="detail-compensation-min">100000' in body2
    assert 'id="detail-compensation-max"' not in body2
    assert 'id="detail-compensation-basis">ANNUAL<' in body2


def test_job_url_rendered_as_clickable_link(client, db_path):
    _post_application(client, job_url="https://example.com/job")
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert '<a id="detail-job-url-link" href="https://example.com/job">' in body


def test_javascript_scheme_job_url_is_not_rendered_as_a_link(client, db_path):
    # A dangerous-scheme job_url can no longer be created through the create
    # form (FR-011 entry-time validation now rejects it directly) - this
    # bypasses that layer with a raw update to verify the detail page's
    # defense-in-depth still holds for values that predate the validation
    # or otherwise reach the database by some other path.
    _post_application(client)
    application_id = _application_id(db_path)
    conn = db.connect(db_path)
    conn.execute(
        "UPDATE application SET job_url = ? WHERE application_id = ?",
        ("javascript:alert(document.cookie)", application_id),
    )
    conn.commit()
    conn.close()

    body = client.get(f"/applications/{application_id}").data.decode()

    assert 'href="javascript:' not in body
    assert 'id="detail-job-url-link"' not in body
    assert "javascript:alert(document.cookie)" in body


def test_http_and_https_job_urls_are_rendered_as_links(client, db_path):
    _post_application(client, job_url="http://example.com/job")
    application_id = _application_id(db_path)
    body = client.get(f"/applications/{application_id}").data.decode()
    assert '<a id="detail-job-url-link" href="http://example.com/job">' in body

    _post_application(client, job_title="Engineer 2", job_url="https://example.com/job")
    application_id2 = _application_id(db_path)
    body2 = client.get(f"/applications/{application_id2}").data.decode()
    assert '<a id="detail-job-url-link" href="https://example.com/job">' in body2


def test_status_history_displayed_oldest_to_newest_with_current_marked(
    client, db_path
):
    _post_application(client)
    application_id = _application_id(db_path)

    conn = db.connect(db_path)
    applied_history_id = conn.execute(
        "SELECT application_status_history_id FROM application_status_history "
        "WHERE application_id = ?",
        (application_id,),
    ).fetchone()["application_status_history_id"]
    screening_id = conn.execute(
        "SELECT status_id FROM status WHERE name = 'SCREENING'"
    ).fetchone()["status_id"]
    cursor = conn.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, '2030-01-01T00:00:00.000Z')",
        (application_id, screening_id),
    )
    screening_history_id = cursor.lastrowid
    conn.commit()
    conn.close()

    body = client.get(f"/applications/{application_id}").data.decode()
    table_html = body[body.index('id="status-history-table"') :]

    assert table_html.index("APPLIED") < table_html.index("SCREENING")

    applied_row_start = table_html.index(
        f'id="status-history-row-{applied_history_id}"'
    )
    screening_row_start = table_html.index(
        f'id="status-history-row-{screening_history_id}"'
    )
    applied_row_html = table_html[applied_row_start:screening_row_start]
    screening_row_html = table_html[screening_row_start:]

    assert 'aria-current="true"' not in applied_row_html
    assert 'aria-current="true"' in screening_row_html


def test_list_page_links_to_detail_page(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    client.get("/applications")  # drain any pending flash message
    body = client.get("/applications").data.decode()

    assert f'id="view-application-{application_id}"' in body
    assert f'href="/applications/{application_id}"' in body


def test_detail_page_escapes_reflected_notes(client, db_path):
    _post_application(client, notes="<script>alert(1)</script>")
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_back_link_to_applications_list_present(client, db_path):
    _post_application(client)
    application_id = _application_id(db_path)

    body = client.get(f"/applications/{application_id}").data.decode()

    assert 'href="/applications"' in body
