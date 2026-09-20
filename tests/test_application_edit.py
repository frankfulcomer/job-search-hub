import sqlite3
from datetime import date, datetime, timezone

import pytest

from job_hub import db
from job_hub.applications import (
    LocationInput,
    SharedHeadquartersChangeRequiresConfirmation,
    ValidationError,
    create_application,
    edit_application,
    get_application_detail,
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
    }
    fields.update(overrides)
    return create_application(connection, **fields)


def _base_edit_fields(**overrides):
    fields = {
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "application_date": date(2026, 9, 20),
        "source_name": "Job Board",
    }
    fields.update(overrides)
    return fields


def test_edit_application_returns_none_for_nonexistent_id(connection):
    assert edit_application(connection, 999, **_base_edit_fields()) is None


def test_edit_application_updates_editable_fields(connection):
    result = _create(connection)

    edit_application(
        connection,
        result.application_id,
        **_base_edit_fields(
            job_title="Senior Engineer",
            notes="Updated notes",
            work_arrangement="REMOTE",
        ),
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.job_title == "Senior Engineer"
    assert detail.notes == "Updated notes"
    assert detail.work_arrangement == "REMOTE"


def test_edit_application_does_not_modify_status_history(connection):
    result = _create(connection)
    before = get_application_detail(connection, result.application_id).status_history

    edit_application(
        connection, result.application_id, **_base_edit_fields(job_title="New Title")
    )

    after = get_application_detail(connection, result.application_id).status_history
    assert len(after) == len(before) == 1
    assert after[0].status_name == before[0].status_name == "APPLIED"
    assert after[0].effective_at == before[0].effective_at


def test_edit_application_preserves_created_at_and_advances_last_updated_at(
    connection,
):
    result = _create(connection)
    before = connection.execute(
        "SELECT created_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()

    import time

    time.sleep(0.01)
    edit_application(
        connection, result.application_id, **_base_edit_fields(job_title="New Title")
    )

    after = connection.execute(
        "SELECT created_at, last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()
    assert after["created_at"] == before["created_at"]
    assert after["last_updated_at"] > before["last_updated_at"]


def test_edit_application_noop_edit_does_not_advance_last_updated_at(connection):
    result = _create(connection)
    before = connection.execute(
        "SELECT last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["last_updated_at"]

    import time

    time.sleep(0.01)
    edit_application(connection, result.application_id, **_base_edit_fields())

    after = connection.execute(
        "SELECT last_updated_at FROM application WHERE application_id = ?",
        (result.application_id,),
    ).fetchone()["last_updated_at"]
    assert after == before


def test_edit_application_reassociates_to_existing_company(connection):
    _create(connection, company_name="Globex")
    result = _create(connection, company_name="Acme Corp")

    edit_application(
        connection, result.application_id, **_base_edit_fields(company_name="Globex")
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.company_name == "Globex"
    companies = connection.execute("SELECT COUNT(*) AS n FROM company").fetchone()["n"]
    assert companies == 2


def test_edit_application_reassociates_to_new_company(connection):
    result = _create(connection)

    edit_result = edit_application(
        connection,
        result.application_id,
        **_base_edit_fields(company_name="Brand New Co"),
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.company_name == "Brand New Co"
    assert edit_result.company_reassigned is True


def test_reassignment_never_applies_submitted_headquarters_even_to_a_new_company(
    connection,
):
    # A brand-new company can't yet be "shared" with any other application,
    # so a submitted headquarters would previously be applied with no
    # confirmation at all - the most severe form of the bug this guards
    # against. Any headquarters submitted alongside a reassignment must be
    # ignored regardless of whether the target company is new or existing.
    result = _create(
        connection,
        company_hq_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    edit_application(
        connection,
        result.application_id,
        **_base_edit_fields(
            company_name="Brand New Co",
            company_hq_location=LocationInput(
                city="Austin", state_province="TX", country="USA"
            ),  # stale value carried over from the previous company
        ),
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.company_name == "Brand New Co"
    assert detail.company_hq_display is None


def test_reassignment_to_existing_company_never_changes_its_headquarters(connection):
    _create(
        connection,
        company_name="Target Co",
        company_hq_location=LocationInput(city="Chicago", state_province="IL", country="USA"),
    )
    result = _create(
        connection,
        company_hq_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    edit_application(
        connection,
        result.application_id,
        **_base_edit_fields(
            company_name="Target Co",
            company_hq_location=LocationInput(
                city="Austin", state_province="TX", country="USA"
            ),  # stale value carried over from the previous company
        ),
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.company_name == "Target Co"
    assert detail.company_hq_display == "Chicago, IL, USA"


def test_reassignment_to_a_shared_company_does_not_require_confirmation(connection):
    # Since the submitted headquarters is never applied on reassignment,
    # there is nothing requiring confirmation at this step, even though the
    # target company is shared by other applications.
    _create(connection, company_name="Shared Co")
    _create(connection, company_name="Shared Co")
    solo = _create(connection, company_name="Solo Co")

    edit_result = edit_application(
        connection,
        solo.application_id,
        **_base_edit_fields(
            company_name="Shared Co",
            company_hq_location=LocationInput(
                city="Seattle", state_province="WA", country="USA"
            ),
        ),
    )

    assert edit_result.company_reassigned is True
    detail = get_application_detail(connection, solo.application_id)
    assert detail.company_name == "Shared Co"


def test_headquarters_can_be_edited_as_a_separate_followup_after_reassignment(
    connection,
):
    _create(connection, company_name="Shared Co")
    _create(connection, company_name="Shared Co")
    solo = _create(connection, company_name="Solo Co")

    edit_application(
        connection, solo.application_id, **_base_edit_fields(company_name="Shared Co")
    )

    # Company is now already "Shared Co" - this second edit is not a
    # reassignment, so headquarters changes go through the normal
    # (confirmation-gated, since the company is shared) path.
    with pytest.raises(SharedHeadquartersChangeRequiresConfirmation):
        edit_application(
            connection,
            solo.application_id,
            **_base_edit_fields(
                company_name="Shared Co",
                company_hq_location=LocationInput(
                    city="Seattle", state_province="WA", country="USA"
                ),
            ),
        )


def test_editing_headquarters_on_unshared_company_applies_without_confirmation(
    connection,
):
    result = _create(
        connection,
        company_hq_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    edit_application(
        connection,
        result.application_id,
        **_base_edit_fields(
            company_hq_location=LocationInput(city="Denver", state_province="CO", country="USA")
        ),
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.company_hq_display == "Denver, CO, USA"


def test_editing_headquarters_on_shared_company_requires_confirmation(connection):
    r1 = _create(
        connection,
        company_hq_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )
    _create(connection)  # second application sharing the same company

    with pytest.raises(SharedHeadquartersChangeRequiresConfirmation) as exc_info:
        edit_application(
            connection,
            r1.application_id,
            **_base_edit_fields(
                company_hq_location=LocationInput(
                    city="Chicago", state_province="IL", country="USA"
                )
            ),
        )

    assert exc_info.value.company_name == "Acme Corp"
    assert exc_info.value.affected_application_count == 1
    assert exc_info.value.current_headquarters_display == "Austin, TX, USA"
    assert exc_info.value.new_headquarters_display == "Chicago, IL, USA"

    detail = get_application_detail(connection, r1.application_id)
    assert detail.company_hq_display == "Austin, TX, USA"
    assert detail.job_title == "Engineer"


def test_confirmed_shared_headquarters_change_applies_to_all_sharing_applications(
    connection,
):
    r1 = _create(
        connection,
        company_hq_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )
    r2 = _create(connection)

    edit_application(
        connection,
        r1.application_id,
        **_base_edit_fields(
            company_hq_location=LocationInput(
                city="Chicago", state_province="IL", country="USA"
            ),
            confirm_shared_headquarters_change=True,
        ),
    )

    assert get_application_detail(connection, r1.application_id).company_hq_display == (
        "Chicago, IL, USA"
    )
    assert get_application_detail(connection, r2.application_id).company_hq_display == (
        "Chicago, IL, USA"
    )


def test_reassigning_company_does_not_leak_previous_companys_headquarters(
    connection,
):
    # The scenario the fix specifically targets: a user reassigns Solo Co's
    # application to Beta Inc (shared) but the form still carries Solo Co's
    # own headquarters (nothing refreshed it client-side). That stale value
    # must never be interpreted as an intended change to Beta Inc.
    _create(connection, company_name="Beta Inc")
    _create(
        connection, company_name="Beta Inc"
    )  # second application makes Beta Inc "shared"
    solo = _create(
        connection,
        company_name="Solo Co",
        company_hq_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    edit_application(
        connection,
        solo.application_id,
        **_base_edit_fields(
            company_name="Beta Inc",
            company_hq_location=LocationInput(
                city="Austin", state_province="TX", country="USA"
            ),  # Solo Co's headquarters, not Beta Inc's
        ),
    )

    detail = get_application_detail(connection, solo.application_id)
    assert detail.company_name == "Beta Inc"
    assert detail.company_hq_display is None


def test_validation_failure_persists_nothing(connection):
    result = _create(connection)
    companies_before = connection.execute(
        "SELECT COUNT(*) AS n FROM company"
    ).fetchone()["n"]

    with pytest.raises(ValidationError):
        edit_application(
            connection, result.application_id, **_base_edit_fields(job_title="")
        )

    detail = get_application_detail(connection, result.application_id)
    assert detail.job_title == "Engineer"
    companies_after = connection.execute(
        "SELECT COUNT(*) AS n FROM company"
    ).fetchone()["n"]
    assert companies_after == companies_before


def test_job_location_can_be_cleared(connection):
    result = _create(
        connection,
        job_location=LocationInput(city="Austin", state_province="TX", country="USA"),
    )

    edit_application(
        connection,
        result.application_id,
        **_base_edit_fields(job_location=LocationInput()),
    )

    detail = get_application_detail(connection, result.application_id)
    assert detail.job_location_display is None


def test_database_constraint_failure_rolls_back(connection):
    result = _create(connection)

    with pytest.raises(sqlite3.IntegrityError):
        edit_application(
            connection,
            result.application_id,
            **_base_edit_fields(
                job_title="Changed Title",
                compensation_min=200000,
                compensation_max=100000,
                compensation_basis="ANNUAL",
            ),
        )

    detail = get_application_detail(connection, result.application_id)
    assert detail.job_title == "Engineer"
    assert detail.compensation_min is None
