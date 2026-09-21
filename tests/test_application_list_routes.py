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
    # Fixed, clearly-past dates (not "today") so this test's outcome can't
    # depend on the real date when it happens to run. The original version
    # posted "Newer Co" with application_date="2026-09-20" and no explicit
    # initial_status_effective_at, relying on create_application's "APPLIED
    # status + application_date is today" shortcut to supply one - which
    # silently stopped applying, and the post silently stopped creating an
    # application at all, once the real date moved past 2026-09-20. Neither
    # application here depends on "today" in any way.
    _post_application(
        client,
        company_name="Older Co",
        application_date="2020-01-01",
        initial_status_effective_at="2020-01-01T09:00",
    )
    _post_application(
        client,
        company_name="Newer Co",
        application_date="2020-06-15",
        initial_status_effective_at="2020-06-15T09:00",
    )

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


# --- FR-004: search and filter -----------------------------------------------


def test_search_filter_form_renders_expected_fields(client):
    # Post one application first so the Source checkbox group (populated
    # from sources actually in use) isn't empty.
    _post_application(client)
    client.get("/applications")  # drain the pending flash message

    body = client.get("/applications").data.decode()

    assert 'id="search-filter-form"' in body
    assert 'id="q"' in body
    assert 'name="status"' in body
    assert 'name="source"' in body
    assert 'name="work_arrangement"' in body
    assert 'name="employment_type"' in body
    assert 'id="job_location"' in body
    assert 'id="date_from"' in body
    assert 'id="date_to"' in body
    assert 'id="apply-filters"' in body
    assert 'id="clear-filters"' in body


def test_search_query_filters_the_list(client):
    _post_application(client, company_name="Acme Corp", job_title="Backend Engineer")
    _post_application(client, company_name="Initech", job_title="Office Manager")
    client.get("/applications")  # drain pending flash messages

    body = client.get("/applications?q=engineer").data.decode()

    assert "Acme Corp" in body
    assert "Initech" not in body
    assert 'value="engineer"' in body


def test_status_filter_narrows_the_list(client):
    # Fixed, clearly-past dates throughout (rather than "today") so this
    # test can't become flaky depending on what time it happens to run -
    # both the initial effective_at and the later status-change effective_at
    # must never risk being evaluated as "in the future".
    _post_application(
        client,
        company_name="Applied Co",
        application_date="2020-01-01",
        initial_status_effective_at="2020-01-01T00:01",
    )
    _post_application(
        client,
        company_name="Screening Co",
        application_date="2020-01-01",
        initial_status_effective_at="2020-01-01T00:01",
    )
    client.post(
        "/applications/2/status",
        data={"status_name": "SCREENING", "effective_at": "2020-01-01T00:02"},
    )
    client.get("/applications")  # drain pending flash messages

    body = client.get("/applications?status=SCREENING").data.decode()

    assert "Screening Co" in body
    assert "Applied Co" not in body


def test_work_arrangement_filter_narrows_the_list(client):
    _post_application(client, company_name="Remote Co", work_arrangement="REMOTE")
    _post_application(client, company_name="Onsite Co", work_arrangement="ONSITE")
    client.get("/applications")  # drain pending flash messages

    body = client.get("/applications?work_arrangement=REMOTE").data.decode()

    assert "Remote Co" in body
    assert "Onsite Co" not in body


def test_source_filter_narrows_the_list(client):
    _post_application(client, company_name="LinkedIn Co", source_name="LinkedIn")
    _post_application(client, company_name="Referral Co", source_name="Referral")
    client.get("/applications")  # drain pending flash messages

    body = client.get("/applications?source=LinkedIn").data.decode()

    assert "LinkedIn Co" in body
    assert "Referral Co" not in body


def test_employment_type_filter_narrows_the_list(client):
    _post_application(client, company_name="Contract Co", employment_type="CONTRACT")
    _post_application(client, company_name="Full Time Co", employment_type="FULL_TIME")
    client.get("/applications")  # drain pending flash messages

    body = client.get("/applications?employment_type=CONTRACT").data.decode()

    assert "Contract Co" in body
    assert "Full Time Co" not in body


def test_job_location_filter_narrows_the_list(client):
    _post_application(
        client,
        company_name="Austin Co",
        job_location_city="Austin",
        job_location_state_province="TX",
        job_location_country="USA",
    )
    _post_application(
        client,
        company_name="Denver Co",
        job_location_city="Denver",
        job_location_state_province="CO",
        job_location_country="USA",
    )
    client.get("/applications")  # drain pending flash messages

    body = client.get("/applications").data.decode()
    import re

    m = re.search(r'<option value="(\d+)"[^>]*>Austin, TX, USA</option>', body)
    assert m, "expected an Austin, TX, USA option in the job location filter"
    location_id = m.group(1)

    filtered = client.get(f"/applications?job_location={location_id}").data.decode()
    assert "Austin Co" in filtered
    assert "Denver Co" not in filtered


def test_date_range_filter_narrows_the_list(client):
    _post_application(
        client,
        company_name="Old Co",
        application_date="2026-09-01",
        initial_status_effective_at="2026-09-01T09:00",
    )
    _post_application(client, company_name="Today Co")
    client.get("/applications")  # drain pending flash messages

    body = client.get(
        f"/applications?date_from={date.today().isoformat()}"
    ).data.decode()

    assert "Today Co" in body
    assert "Old Co" not in body


def test_categories_combine_with_and_filters_combine_with_or(client):
    _post_application(
        client, company_name="Match Co", work_arrangement="REMOTE", source_name="LinkedIn"
    )
    _post_application(
        client, company_name="Wrong Source", work_arrangement="REMOTE", source_name="Referral"
    )
    _post_application(
        client, company_name="Wrong Arrangement", work_arrangement="ONSITE", source_name="LinkedIn"
    )
    client.get("/applications")  # drain pending flash messages

    body = client.get(
        "/applications?work_arrangement=REMOTE&source=LinkedIn"
    ).data.decode()

    assert "Match Co" in body
    assert "Wrong Source" not in body
    assert "Wrong Arrangement" not in body


def test_no_matches_shows_filtered_empty_message(client):
    _post_application(client, company_name="Acme Corp")
    client.get("/applications")  # drain pending flash message

    body = client.get("/applications?q=nonexistent").data.decode()

    assert 'id="applications-empty-state"' in body
    assert "No applications match the current search and filter criteria." in body


def test_invalid_date_range_shows_error_and_excludes_results(client):
    _post_application(client, company_name="Acme Corp")
    client.get("/applications")  # drain pending flash message

    response = client.get("/applications?date_from=2026-09-20&date_to=2026-09-01")
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert "Acme Corp" not in body
    assert 'value="2026-09-20"' in body


def test_malformed_date_shows_error_and_preserves_raw_value(client):
    response = client.get("/applications?date_from=not-a-date")
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="form-error"' in body
    assert 'value="not-a-date"' in body


def test_date_range_ordering_violation_marks_both_date_fields_invalid(client):
    body = client.get(
        "/applications?date_from=2026-09-20&date_to=2026-09-01"
    ).data.decode()

    from_start = body.index('id="date_from"')
    from_end = body.index("</div>", from_start)
    to_start = body.index('id="date_to"')
    to_end = body.index("</div>", to_start)

    assert 'aria-invalid="true"' in body[from_start:from_end]
    assert 'aria-invalid="true"' in body[to_start:to_end]


def test_malformed_single_date_field_marks_only_that_field_invalid(client):
    from_body = client.get("/applications?date_from=not-a-date").data.decode()
    from_start = from_body.index('id="date_from"')
    from_end = from_body.index("</div>", from_start)
    to_start = from_body.index('id="date_to"')
    to_end = from_body.index("</div>", to_start)
    assert 'aria-invalid="true"' in from_body[from_start:from_end]
    assert 'aria-invalid="true"' not in from_body[to_start:to_end]

    to_body = client.get("/applications?date_to=not-a-date").data.decode()
    from_start = to_body.index('id="date_from"')
    from_end = to_body.index("</div>", from_start)
    to_start = to_body.index('id="date_to"')
    to_end = to_body.index("</div>", to_start)
    assert 'aria-invalid="true"' not in to_body[from_start:from_end]
    assert 'aria-invalid="true"' in to_body[to_start:to_end]


def test_oversized_job_location_does_not_error(client):
    response = client.get(
        "/applications?job_location=999999999999999999999999999999"
    )
    body = response.data.decode()

    assert response.status_code == 200
    assert 'id="applications-empty-state"' in body
    assert 'id="form-error"' not in body


def test_negative_oversized_job_location_does_not_error(client):
    response = client.get(
        "/applications?job_location=-999999999999999999999999999999"
    )

    assert response.status_code == 200


def test_oversized_job_location_does_not_hide_unrelated_active_applications(client):
    _post_application(client, company_name="Acme Corp")
    client.get("/applications")  # drain pending flash message

    # Combined with an out-of-range job_location, the request should still
    # be a normal (empty) response rather than a server error, and other
    # applications remain visible once the broken filter is removed.
    response = client.get(
        "/applications?job_location=999999999999999999999999999999"
    )
    assert response.status_code == 200
    assert "Acme Corp" not in response.data.decode()

    body = client.get("/applications").data.decode()
    assert "Acme Corp" in body


def test_clear_filters_link_points_to_unfiltered_list(client):
    body = client.get("/applications?q=engineer&status=APPLIED&state=archived").data.decode()

    idx = body.index('id="clear-filters"')
    snippet = body[idx : idx + 120]
    assert 'href="/applications"' in snippet


def test_sort_header_preserves_active_search(client):
    _post_application(client, company_name="Acme Corp", job_title="Engineer")

    body = client.get("/applications?q=engineer").data.decode()
    idx = body.index('id="sort-company"')
    snippet = body[idx : idx + 250]

    assert "q=engineer" in snippet


def test_pagination_preserves_active_filter(client, db_path):
    from job_hub import db as job_db

    connection = job_db.connect(db_path)
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.execute("INSERT INTO source (name) VALUES ('Job Board')")
    applied_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'APPLIED'"
    ).fetchone()["status_id"]
    for i in range(30):
        cursor = connection.execute(
            "INSERT INTO application "
            "(company_id, source_id, job_title, application_date, work_arrangement) "
            "VALUES (1, 1, ?, '2026-09-20', 'REMOTE')",
            (f"Role {i}",),
        )
        connection.execute(
            "INSERT INTO application_status_history "
            "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
            (cursor.lastrowid, applied_id, f"2026-09-20T{i % 24:02d}:00:00.000Z"),
        )
    connection.commit()
    connection.close()

    body = client.get("/applications?work_arrangement=REMOTE").data.decode()
    assert 'id="page-next"' in body
    idx = body.index('id="page-next"')
    snippet = body[idx : idx + 250]

    assert "work_arrangement=REMOTE" in snippet


def test_record_state_nav_preserves_active_filter(client):
    _post_application(client, company_name="Acme Corp", work_arrangement="REMOTE")

    body = client.get("/applications?work_arrangement=REMOTE").data.decode()
    idx = body.index('id="record-state-archived"')
    snippet = body[idx : idx + 250]

    assert "work_arrangement=REMOTE" in snippet


def test_checkbox_reflects_selected_filter_value(client):
    body = client.get("/applications?status=SCREENING").data.decode()

    idx = body.index('value="SCREENING"')
    snippet = body[idx : idx + 60]
    assert "checked" in snippet

    idx = body.index('value="APPLIED"')
    snippet = body[idx : idx + 60]
    assert "checked" not in snippet
