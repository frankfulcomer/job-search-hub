import sqlite3
import time

import pytest

from job_hub import db

EXPECTED_TABLES = {
    "application",
    "application_status_history",
    "company",
    "location",
    "source",
    "status",
}

WHITESPACE_ONLY_VALUES = [" ", "\t", "\r", "\n", " \t\r\n "]

EXPECTED_STATUSES = [
    ("APPLIED", 0, 1),
    ("SCREENING", 0, 2),
    ("INTERVIEWING", 0, 3),
    ("OFFER", 0, 4),
    ("ACCEPTED", 1, 5),
    ("REJECTED", 1, 6),
    ("WITHDRAWN", 1, 7),
    ("CLOSED", 1, 8),
]


@pytest.fixture
def connection(tmp_path):
    conn = db.connect(str(tmp_path / "test.sqlite3"))
    db.init_db(conn)
    yield conn
    conn.close()


def test_connect_enables_foreign_keys(tmp_path):
    conn = db.connect(str(tmp_path / "fk.sqlite3"))

    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_init_db_creates_all_six_tables(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()

    assert {row["name"] for row in rows} == EXPECTED_TABLES


def test_init_db_seeds_status_reference_data_in_order(connection):
    rows = connection.execute(
        "SELECT name, is_terminal, display_order FROM status ORDER BY display_order"
    ).fetchall()

    assert [(r["name"], r["is_terminal"], r["display_order"]) for r in rows] == (
        EXPECTED_STATUSES
    )


def test_init_db_is_idempotent_and_preserves_existing_data(connection):
    connection.execute("INSERT INTO source (name) VALUES ('Job Board')")
    connection.commit()

    db.init_db(connection)

    sources = connection.execute("SELECT name FROM source").fetchall()
    statuses = connection.execute("SELECT COUNT(*) AS n FROM status").fetchone()

    assert [row["name"] for row in sources] == ["Job Board"]
    assert statuses["n"] == len(EXPECTED_STATUSES)


def test_foreign_key_violation_is_rejected(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application_status_history "
            "(application_id, status_id, effective_at) VALUES "
            "(999, 1, '2026-01-01T00:00:00.000Z')"
        )


def test_company_name_uniqueness_ignores_case_and_whitespace(connection):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO company (name) VALUES ('  acme corp  ')")


@pytest.mark.parametrize("value", WHITESPACE_ONLY_VALUES)
def test_company_name_rejects_whitespace_only_values(connection, value):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO company (name) VALUES (?)", (value,))


@pytest.mark.parametrize("value", WHITESPACE_ONLY_VALUES)
def test_source_name_rejects_whitespace_only_values(connection, value):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO source (name) VALUES (?)", (value,))


def test_application_job_title_rejects_whitespace_only_value(connection):
    _insert_company_and_source(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application (company_id, source_id, job_title, application_date) "
            "VALUES (1, 1, ?, '2026-09-20')",
            (" \t\r\n ",),
        )


def test_company_name_normalization_treats_tabs_and_newlines_as_insignificant(
    connection,
):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO company (name) VALUES (?)", ("\tAcme Corp\n",)
        )


def test_location_reuse_ignores_case_and_whitespace(connection):
    connection.execute(
        "INSERT INTO location (city, state_province, country) "
        "VALUES ('Austin', 'TX', 'USA')"
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO location (city, state_province, country) "
            "VALUES ('  AUSTIN ', ' tx ', ' usa ')"
        )


def test_location_requires_at_least_one_component(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO location (city, state_province, country) "
            "VALUES (NULL, NULL, NULL)"
        )


@pytest.mark.parametrize("value", WHITESPACE_ONLY_VALUES)
def test_location_whitespace_only_component_does_not_count_as_present(
    connection, value
):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO location (city, state_province, country) "
            "VALUES (?, NULL, NULL)",
            (value,),
        )


def test_location_normalization_treats_tabs_and_newlines_as_insignificant(
    connection,
):
    connection.execute(
        "INSERT INTO location (city, state_province, country) "
        "VALUES ('Austin', 'TX', 'USA')"
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO location (city, state_province, country) "
            "VALUES (?, 'TX', 'USA')",
            ("\tAustin\n",),
        )


def _insert_company_and_source(connection):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.execute("INSERT INTO source (name) VALUES ('Job Board')")
    connection.commit()


def test_status_history_unique_application_and_effective_at(connection):
    _insert_company_and_source(connection)
    connection.execute(
        "INSERT INTO application (company_id, source_id, job_title, application_date) "
        "VALUES (1, 1, 'Engineer', '2026-09-20')"
    )
    connection.commit()
    connection.execute(
        "INSERT INTO application_status_history "
        "(application_id, status_id, effective_at) VALUES "
        "(1, 1, '2026-09-20T09:00:00.000Z')"
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application_status_history "
            "(application_id, status_id, effective_at) VALUES "
            "(1, 2, '2026-09-20T09:00:00.000Z')"
        )


def test_compensation_min_must_not_exceed_max(connection):
    _insert_company_and_source(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application "
            "(company_id, source_id, job_title, application_date, "
            "compensation_min, compensation_max, compensation_basis) "
            "VALUES (1, 1, 'Engineer', '2026-09-20', 200000, 100000, 'ANNUAL')"
        )


def test_compensation_basis_required_when_compensation_present(connection):
    _insert_company_and_source(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application "
            "(company_id, source_id, job_title, application_date, compensation_min) "
            "VALUES (1, 1, 'Engineer', '2026-09-20', 100000)"
        )


def test_compensation_column_rejects_non_numeric_value(connection):
    _insert_company_and_source(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application "
            "(company_id, source_id, job_title, application_date, "
            "compensation_min, compensation_basis) "
            "VALUES (1, 1, 'Engineer', '2026-09-20', 'not-a-number', 'ANNUAL')"
        )


def test_work_arrangement_rejects_invalid_value(connection):
    _insert_company_and_source(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO application "
            "(company_id, source_id, job_title, application_date, work_arrangement) "
            "VALUES (1, 1, 'Engineer', '2026-09-20', 'FROM_THE_MOON')"
        )


def test_created_at_and_last_updated_at_are_populated_on_insert(connection):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.commit()

    row = connection.execute(
        "SELECT created_at, last_updated_at FROM company"
    ).fetchone()

    assert row["created_at"] == row["last_updated_at"]
    assert row["created_at"].endswith("Z")


def test_last_updated_at_is_unchanged_by_a_noop_update(connection):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.commit()
    before = connection.execute(
        "SELECT last_updated_at FROM company WHERE company_id = 1"
    ).fetchone()["last_updated_at"]

    time.sleep(0.01)
    connection.execute(
        "UPDATE company SET name = 'Acme Corp' WHERE company_id = 1"
    )
    connection.commit()
    after = connection.execute(
        "SELECT last_updated_at FROM company WHERE company_id = 1"
    ).fetchone()["last_updated_at"]

    assert after == before


def test_last_updated_at_changes_on_update_but_created_at_does_not(connection):
    connection.execute("INSERT INTO company (name) VALUES ('Acme Corp')")
    connection.commit()
    before = connection.execute(
        "SELECT created_at, last_updated_at FROM company WHERE company_id = 1"
    ).fetchone()

    # SQLite timestamp precision is milliseconds; sleep to guarantee the
    # trigger produces a different last_updated_at value.
    time.sleep(0.01)
    connection.execute(
        "UPDATE company SET name = 'Acme Corporation' WHERE company_id = 1"
    )
    connection.commit()
    after = connection.execute(
        "SELECT created_at, last_updated_at FROM company WHERE company_id = 1"
    ).fetchone()

    assert after["created_at"] == before["created_at"]
    assert after["last_updated_at"] > before["last_updated_at"]


def test_get_db_uses_app_configured_database_path(tmp_path):
    from job_hub import create_app

    class TestConfig:
        DATABASE = str(tmp_path / "isolated.sqlite3")

    app = create_app(TestConfig)

    with app.app_context():
        conn = db.get_db()
        db.init_db(conn)

    assert (tmp_path / "isolated.sqlite3").exists()
