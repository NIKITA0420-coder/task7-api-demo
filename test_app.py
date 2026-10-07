from unittest.mock import patch, MagicMock
import requests, app as a

c = a.app.test_client()

def fake(status=200, json=None, headers=None):
    m = MagicMock(); m.status_code = status; m.ok = status < 400
    m.json.return_value = json or {}; m.headers = headers or {}; return m

def test_success_and_headers():
    with patch.object(a.http, "get", return_value=fake(json={"login": "x", "followers": 1, "public_repos": 2})):
        r = c.get("/api/users/x")
    assert r.status_code == 200 and r.headers["X-RateLimit-Limit"] == "3"

def test_rate_limit_429():
    with patch.object(a.http, "get", return_value=fake(json={"login": "y", "followers": 1, "public_repos": 2})):
        codes = [c.get("/api/users/y").status_code for _ in range(5)]
    assert 429 in codes

def test_errors():
    with patch.object(a.http, "get", side_effect=requests.Timeout):
        assert c.get("/api/users/z1").status_code in (504, 429)
    assert c.get("/api/me").status_code == 401
    assert c.get("/nope").status_code == 404
    assert c.get("/callback?state=bad&code=1").status_code == 400
