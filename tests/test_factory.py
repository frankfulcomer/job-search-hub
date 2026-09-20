from job_hub import create_app, db


def _isolated_config(tmp_path):
    class TestConfig:
        DATABASE = str(tmp_path / "test.sqlite3")

    return TestConfig


def test_create_app_returns_flask_app(tmp_path):
    app = create_app(_isolated_config(tmp_path))

    assert app is not None
    assert app.name == "job_hub"


def test_create_app_registers_home_route(tmp_path):
    app = create_app(_isolated_config(tmp_path))

    assert "main.home" in app.view_functions


def test_create_app_automatically_initializes_database_schema(tmp_path):
    app = create_app(_isolated_config(tmp_path))

    with app.app_context():
        statuses = db.get_db().execute("SELECT COUNT(*) AS n FROM status").fetchone()

    assert statuses["n"] == 8


def test_create_app_initialization_is_idempotent_across_repeated_calls(tmp_path):
    config = _isolated_config(tmp_path)

    create_app(config)
    app = create_app(config)

    with app.app_context():
        statuses = db.get_db().execute("SELECT COUNT(*) AS n FROM status").fetchone()

    assert statuses["n"] == 8
