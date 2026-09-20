import pytest

from job_hub import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def test_home_page_returns_200(client):
    response = client.get("/")

    assert response.status_code == 200


def test_home_page_renders_expected_content(client):
    response = client.get("/")

    assert b'id="home-page"' in response.data
    assert b"Welcome to Job Hub" in response.data
