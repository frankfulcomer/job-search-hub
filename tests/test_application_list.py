from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import LocationInput, create_application, list_applications

NOW = datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def connection(tmp_path):
    conn = db.connect(str(tmp_path / "test.sqlite3"))
    db.init_db(conn)
    yield conn
    conn.close()


def _create(connection, **overrides):
    fields = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date(2026, 9, 20),
        "source_name": "Job Board",
        "now": NOW,
    }
    fields.update(overrides)
    return create_application(connection, **fields)


def test_list_applications_is_empty_when_none_exist(connection):
    result = list_applications(connection)

    assert result.items == []
    assert result.total_count == 0
    assert result.total_pages == 1


def test_list_applications_returns_expected_fields(connection):
    _create(
        connection,
        company_name="Acme Corp",
        job_title="Engineer",
        source_name="Job Board",
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    result = list_applications(connection)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.company_name == "Acme Corp"
    assert item.job_title == "Engineer"
    assert item.source_name == "Job Board"
    assert item.status_name == "APPLIED"
    assert item.application_date == "2026-09-20"
    assert item.job_location_display == "Austin, TX, USA"


def test_list_applications_job_location_is_none_when_not_set(connection):
    _create(connection)

    item = list_applications(connection).items[0]

    assert item.job_location_city is None
    assert item.job_location_display is None


def test_list_applications_current_status_reflects_latest_history_not_initial(
    connection,
):
    result = _create(connection)
    screening_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'SCREENING'"
    ).fetchone()["status_id"]
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
        (result.application_id, screening_id, "2026-09-20T16:00:00.000Z"),
    )
    connection.commit()

    item = list_applications(connection).items[0]

    assert item.status_name == "SCREENING"


def test_list_applications_default_order_is_application_date_descending(connection):
    _create(connection, company_name="Older", application_date=date(2026, 9, 1),
            initial_status_effective_at=datetime(2026, 9, 1, 9, tzinfo=timezone.utc))
    _create(connection, company_name="Newer", application_date=date(2026, 9, 20))

    result = list_applications(connection)

    assert [item.company_name for item in result.items] == ["Newer", "Older"]


def test_list_applications_sorts_by_requested_column_ascending(connection):
    _create(connection, company_name="Zeta Corp")
    _create(connection, company_name="Alpha Corp")

    result = list_applications(connection, sort="company", direction="asc")

    assert [item.company_name for item in result.items] == ["Alpha Corp", "Zeta Corp"]


def test_list_applications_sorts_by_status_alphabetically_by_displayed_name(
    connection,
):
    screening = _create(connection, company_name="Screening Co")
    screening_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'SCREENING'"
    ).fetchone()["status_id"]
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
        (screening.application_id, screening_id, "2026-09-20T16:00:00.000Z"),
    )
    connection.commit()
    _create(connection, company_name="Applied Co")

    result = list_applications(connection, sort="status", direction="asc")

    # Alphabetically, APPLIED sorts before SCREENING, even though APPLIED's
    # display_order (lifecycle sequence) is lower than SCREENING's too here -
    # this specific pair doesn't distinguish the two orderings, so also check
    # against a pair where alphabetical and display_order disagree.
    assert [item.status_name for item in result.items] == ["APPLIED", "SCREENING"]


def test_list_applications_status_sort_is_alphabetical_not_lifecycle_order(
    connection,
):
    # OFFER has an earlier display_order than CLOSED but sorts after it
    # alphabetically - this pair distinguishes the two possible orderings.
    offer = _create(connection, company_name="Offer Co")
    offer_status_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'OFFER'"
    ).fetchone()["status_id"]
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
        (offer.application_id, offer_status_id, "2026-09-20T16:00:00.000Z"),
    )
    closed = _create(connection, company_name="Closed Co")
    closed_status_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'CLOSED'"
    ).fetchone()["status_id"]
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES (?, ?, ?)",
        (closed.application_id, closed_status_id, "2026-09-20T16:00:00.000Z"),
    )
    connection.commit()

    result = list_applications(connection, sort="status", direction="asc")

    assert [item.status_name for item in result.items] == ["CLOSED", "OFFER"]


def test_list_applications_sort_direction_toggle_reverses_order(connection):
    _create(connection, company_name="Zeta Corp")
    _create(connection, company_name="Alpha Corp")

    asc = list_applications(connection, sort="company", direction="asc")
    desc = list_applications(connection, sort="company", direction="desc")

    assert [i.company_name for i in asc.items] == list(
        reversed([i.company_name for i in desc.items])
    )


def test_list_applications_invalid_sort_falls_back_to_default(connection):
    _create(connection)

    result = list_applications(connection, sort="not_a_real_column", direction="asc")

    assert result.sort == "application_date"


def test_list_applications_invalid_direction_falls_back_to_default(connection):
    _create(connection)

    result = list_applications(connection, sort="company", direction="sideways")

    assert result.direction == "desc"


def test_list_applications_pagination_math(connection):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.execute("INSERT INTO source (name) VALUES ('Job Board')")
    applied_id = connection.execute(
        "SELECT status_id FROM status WHERE name = 'APPLIED'"
    ).fetchone()["status_id"]
    for i in range(30):
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

    page1 = list_applications(connection, page=1)
    page2 = list_applications(connection, page=2)

    assert page1.total_count == 30
    assert page1.total_pages == 2
    assert len(page1.items) == 25
    assert len(page2.items) == 5
    assert page1.page == 1
    assert page2.page == 2


def test_list_applications_out_of_range_page_clamps_to_last_page(connection):
    _create(connection)

    result = list_applications(connection, page=999)

    assert result.page == 1
    assert len(result.items) == 1


def test_list_applications_excludes_archived_applications(connection):
    result = _create(connection, company_name="Archived Co")
    connection.execute(
        "UPDATE application SET archived_at = '2026-09-20T12:00:00.000Z' "
        "WHERE application_id = ?",
        (result.application_id,),
    )
    connection.commit()

    listed = list_applications(connection)

    assert listed.items == []
    assert listed.total_count == 0
