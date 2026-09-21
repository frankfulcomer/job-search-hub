from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    LocationInput,
    create_application,
    list_applications,
    list_job_location_filter_options,
    list_source_filter_options,
)

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
        # Several list/filter tests deliberately reuse the same
        # company/job-title defaults across multiple applications to
        # isolate the filter dimension under test - not FR-002 duplicate
        # detection, which has its own dedicated test file.
        "confirm_duplicate": True,
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


def _archive(connection, application_id, archived_at="2026-09-20T12:00:00.000Z"):
    connection.execute(
        "UPDATE application SET archived_at = ? WHERE application_id = ?",
        (archived_at, application_id),
    )
    connection.commit()


def test_list_applications_default_record_state_is_active(connection):
    result = list_applications(connection)

    assert result.record_state == "active"


def test_list_applications_record_state_archived_returns_only_archived(connection):
    active = _create(connection, company_name="Active Co")
    archived = _create(connection, company_name="Archived Co")
    _archive(connection, archived.application_id)

    result = list_applications(connection, record_state="archived")

    assert [item.application_id for item in result.items] == [archived.application_id]
    assert result.record_state == "archived"


def test_list_applications_record_state_all_returns_both(connection):
    active = _create(connection, company_name="Active Co")
    archived = _create(connection, company_name="Archived Co")
    _archive(connection, archived.application_id)

    result = list_applications(connection, record_state="all")

    assert {item.application_id for item in result.items} == {
        active.application_id,
        archived.application_id,
    }
    assert result.record_state == "all"


def test_list_applications_all_marks_archived_items(connection):
    active = _create(connection, company_name="Active Co")
    archived = _create(connection, company_name="Archived Co")
    _archive(connection, archived.application_id)

    result = list_applications(connection, record_state="all")

    flags = {item.application_id: item.is_archived for item in result.items}
    assert flags[active.application_id] is False
    assert flags[archived.application_id] is True


def test_list_applications_unrecognized_record_state_falls_back_to_active(connection):
    active = _create(connection, company_name="Active Co")
    archived = _create(connection, company_name="Archived Co")
    _archive(connection, archived.application_id)

    result = list_applications(connection, record_state="not-a-real-state")

    assert [item.application_id for item in result.items] == [active.application_id]
    assert result.record_state == "active"


def test_list_applications_archived_state_sorts_and_paginates_like_active(connection):
    for i in range(3):
        result = _create(connection, company_name=f"Co {i}")
        _archive(connection, result.application_id, f"2026-09-{18 + i}T12:00:00.000Z")

    result = list_applications(
        connection, record_state="archived", sort="company", direction="asc"
    )

    assert [item.company_name for item in result.items] == ["Co 0", "Co 1", "Co 2"]
    assert result.total_count == 3


# --- FR-004: free-text search ---------------------------------------------


def test_search_matches_company(connection):
    match = _create(connection, company_name="Acme Corp")
    _create(connection, company_name="Globex", job_title="Other")

    result = list_applications(connection, search="acme")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_matches_job_title(connection):
    match = _create(connection, job_title="Backend Engineer")
    _create(connection, job_title="Manager")

    result = list_applications(connection, search="engineer")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_matches_external_job_id(connection):
    match = _create(connection, external_job_id="REQ-12345")
    _create(connection, external_job_id="REQ-99999")

    result = list_applications(connection, search="12345")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_is_case_insensitive(connection):
    match = _create(connection, company_name="Acme Corp")

    result = list_applications(connection, search="ACME")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_is_substring_not_prefix_only(connection):
    match = _create(connection, company_name="The Acme Corporation")

    result = list_applications(connection, search="cme corp")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_escapes_percent_wildcard(connection):
    match = _create(connection, company_name="50% Off Staffing")
    _create(connection, company_name="500 Staffing Co")

    result = list_applications(connection, search="50%")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_escapes_underscore_wildcard(connection):
    match = _create(connection, company_name="Acme_Staffing")
    _create(connection, company_name="AcmeXStaffing")

    result = list_applications(connection, search="acme_staffing")

    assert [i.application_id for i in result.items] == [match.application_id]


def test_search_no_match_returns_empty(connection):
    _create(connection, company_name="Acme Corp")

    result = list_applications(connection, search="nonexistent")

    assert result.items == []
    assert result.total_count == 0


def test_blank_search_is_treated_as_no_search(connection):
    _create(connection)

    result = list_applications(connection, search="   ")

    assert len(result.items) == 1
    assert result.search is None


def test_search_is_echoed_back_on_result(connection):
    _create(connection)

    result = list_applications(connection, search="  Engineer  ")

    assert result.search == "Engineer"


# --- FR-004: category filters -----------------------------------------------


def test_status_filter_single_value(connection):
    from job_hub.applications import change_application_status

    match = _create(connection)
    # Explicit earlier initial effective_at so the later status change below
    # (still not in the future relative to NOW) actually becomes current.
    other = _create(
        connection,
        company_name="Other Co",
        initial_status_effective_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    change_application_status(
        connection,
        other.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    result = list_applications(connection, status=["APPLIED"])

    assert [i.application_id for i in result.items] == [match.application_id]


def test_status_filter_multiple_values_combine_with_or(connection):
    from job_hub.applications import change_application_status

    applied = _create(connection, company_name="Applied Co")
    screening = _create(
        connection,
        company_name="Screening Co",
        initial_status_effective_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    offer = _create(
        connection,
        company_name="Offer Co",
        initial_status_effective_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    change_application_status(
        connection,
        screening.application_id,
        status_name="SCREENING",
        effective_at=datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
        now=NOW,
    )
    change_application_status(
        connection,
        offer.application_id,
        status_name="OFFER",
        effective_at=datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    result = list_applications(connection, status=["APPLIED", "SCREENING"])

    assert {i.application_id for i in result.items} == {
        applied.application_id,
        screening.application_id,
    }


def test_source_filter(connection):
    match = _create(connection, source_name="LinkedIn")
    _create(connection, source_name="Referral")

    result = list_applications(connection, source=["LinkedIn"])

    assert [i.application_id for i in result.items] == [match.application_id]


def test_work_arrangement_filter(connection):
    match = _create(connection, work_arrangement="REMOTE")
    _create(connection, work_arrangement="ONSITE")

    result = list_applications(connection, work_arrangement=["REMOTE"])

    assert [i.application_id for i in result.items] == [match.application_id]


def test_employment_type_filter(connection):
    match = _create(connection, employment_type="CONTRACT")
    _create(connection, employment_type="FULL_TIME")

    result = list_applications(connection, employment_type=["CONTRACT"])

    assert [i.application_id for i in result.items] == [match.application_id]


def test_job_location_filter(connection):
    match = _create(
        connection,
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )
    _create(
        connection,
        job_location=LocationInput(city="Denver", state_province="CO", country="USA"),
    )

    options = list_job_location_filter_options(connection)
    austin_id = next(lid for lid, display in options if display == "Austin, TX, USA")

    result = list_applications(connection, job_location_id=austin_id)

    assert [i.application_id for i in result.items] == [match.application_id]


def test_filter_categories_combine_with_and_and_within_category_with_or(connection):
    # Exercises the exact worked example from FR-004: SCREENING/INTERVIEWING
    # status OR'd together, HYBRID/REMOTE work arrangement OR'd together,
    # the two categories AND'd together.
    from job_hub.applications import change_application_status

    initial_at = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    match1 = _create(
        connection,
        company_name="Match 1",
        work_arrangement="HYBRID",
        initial_status_effective_at=initial_at,
    )
    match2 = _create(
        connection,
        company_name="Match 2",
        work_arrangement="REMOTE",
        initial_status_effective_at=initial_at,
    )
    wrong_status = _create(
        connection,
        company_name="Wrong Status",
        work_arrangement="HYBRID",
        initial_status_effective_at=initial_at,
    )
    wrong_arrangement = _create(
        connection,
        company_name="Wrong Arrangement",
        work_arrangement="ONSITE",
        initial_status_effective_at=initial_at,
    )
    for app_result, status_name in (
        (match1, "SCREENING"),
        (match2, "INTERVIEWING"),
        (wrong_status, "OFFER"),
        (wrong_arrangement, "SCREENING"),
    ):
        change_application_status(
            connection,
            app_result.application_id,
            status_name=status_name,
            effective_at=datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
            now=NOW,
        )

    result = list_applications(
        connection,
        status=["SCREENING", "INTERVIEWING"],
        work_arrangement=["HYBRID", "REMOTE"],
    )

    assert {i.application_id for i in result.items} == {
        match1.application_id,
        match2.application_id,
    }


def test_filters_apply_within_the_selected_record_state(connection):
    from job_hub.applications import archive_application

    active_match = _create(connection, company_name="Active Match", work_arrangement="REMOTE")
    archived_match = _create(
        connection, company_name="Archived Match", work_arrangement="REMOTE"
    )
    archive_application(connection, archived_match.application_id, now=NOW)

    active_result = list_applications(connection, work_arrangement=["REMOTE"])
    assert [i.application_id for i in active_result.items] == [active_match.application_id]

    archived_result = list_applications(
        connection, record_state="archived", work_arrangement=["REMOTE"]
    )
    assert [i.application_id for i in archived_result.items] == [
        archived_match.application_id
    ]

    all_result = list_applications(
        connection, record_state="all", work_arrangement=["REMOTE"]
    )
    assert {i.application_id for i in all_result.items} == {
        active_match.application_id,
        archived_match.application_id,
    }


# --- FR-004: application date range -----------------------------------------


def _retrospective(application_date):
    return datetime(
        application_date.year,
        application_date.month,
        application_date.day,
        9,
        0,
        tzinfo=timezone.utc,
    )


def test_date_from_only_excludes_earlier_applications(connection):
    early = _create(
        connection,
        application_date=date(2026, 9, 1),
        initial_status_effective_at=_retrospective(date(2026, 9, 1)),
    )
    late = _create(connection, application_date=date(2026, 9, 20))

    result = list_applications(connection, date_from=date(2026, 9, 10))

    assert [i.application_id for i in result.items] == [late.application_id]


def test_date_to_only_excludes_later_applications(connection):
    early = _create(
        connection,
        application_date=date(2026, 9, 1),
        initial_status_effective_at=_retrospective(date(2026, 9, 1)),
    )
    late = _create(connection, application_date=date(2026, 9, 20))

    result = list_applications(connection, date_to=date(2026, 9, 10))

    assert [i.application_id for i in result.items] == [early.application_id]


def test_date_range_bounds_are_inclusive(connection):
    # NOW is fixed at 2026-09-20; keep this window entirely in the past
    # relative to it so no effective_at ends up rejected as "in the future".
    on_start = _create(
        connection,
        application_date=date(2026, 9, 5),
        initial_status_effective_at=_retrospective(date(2026, 9, 5)),
    )
    on_end = _create(
        connection,
        application_date=date(2026, 9, 15),
        initial_status_effective_at=_retrospective(date(2026, 9, 15)),
    )
    before = _create(
        connection,
        application_date=date(2026, 9, 4),
        initial_status_effective_at=_retrospective(date(2026, 9, 4)),
    )
    after = _create(
        connection,
        application_date=date(2026, 9, 16),
        initial_status_effective_at=_retrospective(date(2026, 9, 16)),
    )

    result = list_applications(
        connection, date_from=date(2026, 9, 5), date_to=date(2026, 9, 15)
    )

    assert {i.application_id for i in result.items} == {
        on_start.application_id,
        on_end.application_id,
    }


# --- FR-004: pagination and sorting under active filters --------------------


def test_filtered_results_paginate_correctly(connection):
    for i in range(30):
        _create(connection, company_name=f"Match {i:02d}", work_arrangement="REMOTE")
    _create(connection, company_name="Not a match", work_arrangement="ONSITE")

    page1 = list_applications(connection, work_arrangement=["REMOTE"], page=1)
    page2 = list_applications(connection, work_arrangement=["REMOTE"], page=2)

    assert page1.total_count == 30
    assert len(page1.items) == 25
    assert len(page2.items) == 5


def test_filtered_results_sort_correctly(connection):
    _create(connection, company_name="Zeta Co", work_arrangement="REMOTE")
    _create(connection, company_name="Alpha Co", work_arrangement="REMOTE")
    _create(connection, company_name="Not a match", work_arrangement="ONSITE")

    result = list_applications(
        connection, work_arrangement=["REMOTE"], sort="company", direction="asc"
    )

    assert [i.company_name for i in result.items] == ["Alpha Co", "Zeta Co"]


# --- FR-004: filter option helpers ------------------------------------------


def test_list_source_filter_options_returns_distinct_used_sources(connection):
    _create(connection, source_name="LinkedIn")
    _create(connection, source_name="Referral")
    _create(connection, source_name="LinkedIn")

    options = list_source_filter_options(connection)

    assert options == ["LinkedIn", "Referral"]


def test_list_job_location_filter_options_returns_distinct_used_locations(connection):
    _create(
        connection,
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )
    _create(
        connection,
        job_location=LocationInput(city="Denver", state_province="CO", country="USA"),
    )
    _create(connection)  # no job location

    options = list_job_location_filter_options(connection)

    displays = [display for _location_id, display in options]
    assert displays == ["Austin, TX, USA", "Denver, CO, USA"]


# --- FR-004: filters echoed back on the result ------------------------------


def test_active_filters_are_echoed_back_on_result(connection):
    _create(connection, work_arrangement="REMOTE", source_name="LinkedIn")

    result = list_applications(
        connection,
        status=["APPLIED"],
        source=["LinkedIn"],
        work_arrangement=["REMOTE"],
        employment_type=["FULL_TIME"],
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.status == ["APPLIED"]
    assert result.source == ["LinkedIn"]
    assert result.work_arrangement == ["REMOTE"]
    assert result.employment_type == ["FULL_TIME"]
    assert result.date_from == date(2026, 9, 1)
    assert result.date_to == date(2026, 9, 30)
