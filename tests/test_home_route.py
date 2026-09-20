import pytest

from job_hub import create_app


@pytest.fixture
def client(tmp_path):
    class TestConfig:
        DATABASE = str(tmp_path / "test.sqlite3")
        TESTING = True

    app = create_app(TestConfig)
    with app.test_client() as client:
        yield client


def test_home_page_returns_200(client):
    response = client.get("/")

    assert response.status_code == 200


def test_home_page_renders_expected_content(client):
    response = client.get("/")

    assert b'id="home-page"' in response.data
    assert b"Welcome to Job Hub" in response.data
