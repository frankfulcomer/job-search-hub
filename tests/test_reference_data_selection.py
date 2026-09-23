from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    LocationInput,
    create_application,
    edit_application,
    list_all_company_names,
    list_all_source_names,
    list_location_component_options,
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
        # This file exercises reference-data listing, which routinely
        # creates several applications sharing a company/job title - not
        # FR-002 duplicate detection, which has its own dedicated test file.
        "confirm_duplicate": True,
    }
    fields.update(overrides)
    return create_application(connection, **fields)


# --- list_all_company_names -------------------------------------------------


def test_list_all_company_names_returns_empty_when_none_exist(connection):
    assert list_all_company_names(connection) == []


def test_list_all_company_names_returns_distinct_sorted_names(connection):
    _create(connection, company_name="Zeta Corp")
    _create(connection, company_name="Alpha Corp")
    _create(connection, company_name="Zeta Corp", job_title="Manager")

    assert list_all_company_names(connection) == ["Alpha Corp", "Zeta Corp"]


def test_list_all_company_names_includes_companies_with_no_current_applications(
    connection,
):
    # Unlike FR-004's filter options (scoped to values currently in use),
    # FR-010's selection list must still offer a company that no longer has
    # any linked application (e.g. after every application referencing it
    # was reassigned elsewhere via edit), since it remains a legitimate,
    # previously-created record that should be reused rather than
    # accidentally re-created as a near-duplicate.
    result = _create(connection, company_name="Orphaned Co")

    edit_application(
        connection,
        result.application_id,
        company_name="Different Co",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
    )

    assert "Orphaned Co" in list_all_company_names(connection)


# --- list_all_source_names --------------------------------------------------


def test_list_all_source_names_returns_empty_when_none_exist(connection):
    assert list_all_source_names(connection) == []


def test_list_all_source_names_returns_distinct_sorted_names(connection):
    _create(connection, source_name="LinkedIn")
    _create(connection, source_name="Referral")
    _create(connection, source_name="LinkedIn", job_title="Manager")

    assert list_all_source_names(connection) == ["LinkedIn", "Referral"]


def test_list_all_source_names_includes_sources_with_no_current_applications(
    connection,
):
    result = _create(connection, source_name="Orphaned Source")

    edit_application(
        connection,
        result.application_id,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Different Source",
    )

    assert "Orphaned Source" in list_all_source_names(connection)


# --- list_location_component_options ----------------------------------------


def test_list_location_component_options_returns_empty_lists_when_none_exist(
    connection,
):
    options = list_location_component_options(connection)

    assert options.cities == []
    assert options.state_provinces == []
    assert options.countries == []


def test_list_location_component_options_returns_distinct_sorted_components(
    connection,
):
    _create(
        connection,
        company_name="Austin Co",
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )
    _create(
        connection,
        company_name="Denver Co",
        job_location=LocationInput(city="Denver", state_province="CO", country="USA"),
    )
    _create(
        connection,
        company_name="Second Austin Co",
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    options = list_location_component_options(connection)

    assert options.cities == ["Austin", "Denver"]
    assert options.state_provinces == ["CO", "TX"]
    assert options.countries == ["USA"]


def test_list_location_component_options_includes_company_headquarters_locations(
    connection,
):
    # Company headquarters and job location share the same LOCATION table;
    # a city used only as a headquarters should still be suggested.
    _create(
        connection,
        company_hq_location=LocationInput(
            city="Seattle", state_province="WA", country="USA"
        ),
    )

    options = list_location_component_options(connection)

    assert "Seattle" in options.cities
    assert "WA" in options.state_provinces


def test_list_location_component_options_omits_none_components(connection):
    # A location with only some components set (e.g. country but no city)
    # must not contribute a None/blank suggestion for the missing ones.
    _create(connection, job_location=LocationInput(country="USA"))

    options = list_location_component_options(connection)

    assert options.cities == []
    assert options.state_provinces == []
    assert options.countries == ["USA"]


def test_list_location_component_options_includes_locations_with_no_current_applications(
    connection,
):
    result = _create(
        connection,
        job_location=LocationInput(
            city="Orphan City", state_province="OZ", country="Oz"
        ),
    )

    edit_application(
        connection,
        result.application_id,
        company_name="Acme Corp",
        job_title="Engineer",
        application_date=date(2026, 9, 20),
        source_name="Job Board",
        job_location=LocationInput(),
    )

    options = list_location_component_options(connection)
    assert "Orphan City" in options.cities
