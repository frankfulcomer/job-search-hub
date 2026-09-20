from job_hub import create_app


def test_create_app_returns_flask_app():
    app = create_app()

    assert app is not None
    assert app.name == "job_hub"


def test_create_app_registers_home_route():
    app = create_app()

    assert "main.home" in app.view_functions
