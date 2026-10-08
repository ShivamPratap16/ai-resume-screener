from fastapi.testclient import TestClient

from screener.api import app

from conftest import JAVA_REACT_ONLY, THIN_WRAPPER


def test_screen_then_results():
    client = TestClient(app)
    files = [
        ("files", ("thin.txt", THIN_WRAPPER.encode(), "text/plain")),
        ("files", ("java.txt", JAVA_REACT_ONLY.encode(), "text/plain")),
    ]
    response = client.post("/screen", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["eligible"] == 1 and body["summary"]["rejected"] == 1
    assert client.get("/results").json() == body
