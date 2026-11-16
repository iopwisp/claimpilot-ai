from uuid import uuid4

from test_claims import account


def test_browser_session_guards_and_revocation(client):
    admin, _ = account(client, "admin")
    credentials = {"email": f"{uuid4()}@example.invalid", "password": uuid4().hex}
    user = client.post("/api/v1/auth/register", json=credentials).json()
    headers = {"X-ClaimPilot-Request": "browser"}
    login = client.post("/api/v1/auth/login", json=credentials, headers=headers)
    assert "access_token" not in login.json()
    assert "HttpOnly" in login.headers["set-cookie"] and "SameSite=strict" in login.headers["set-cookie"]
    assert client.get("/api/v1/auth/me").json()["id"] == user["id"]
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.get("/api/v1/claims").headers["Cache-Control"] == "no-store"
    client.patch(
        "/api/v1/users/" + user["id"], headers=admin, json={"role": "reviewer"}
    ).raise_for_status()
    assert client.get("/api/v1/auth/me").status_code == 401
    client.post("/api/v1/auth/login", json=credentials, headers=headers).raise_for_status()
    client.post("/api/v1/auth/logout", headers=headers).raise_for_status()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_password_not_reflected(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "test@example.invalid", "password": "private"}
    )
    assert response.status_code == 422 and "private" not in response.text


def test_operator_can_close_registration(client, monkeypatch):
    monkeypatch.setenv("ALLOW_REGISTRATION", "0")
    assert client.get("/api/v1/auth/options").json() == {"registration_open": False}
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": "closed@example.invalid", "password": uuid4().hex}
        ).status_code
        == 403
    )
