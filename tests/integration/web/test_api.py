"""Интеграционные тесты HTTP API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from composition.app import create_app
from infrastructure.persistence.in_memory_session_store import InMemorySessionStore
from infrastructure.tts.null_tts import NullTTS


@pytest.fixture
def client() -> TestClient:
    app = create_app(store=InMemorySessionStore(), tts=NullTTS())
    return TestClient(app)


@pytest.mark.integration
def test_create_session_returns_menu(client: TestClient) -> None:
    res = client.post("/api/sessions")
    assert res.status_code == 201
    body = res.json()
    assert body["state"] == "MENU"
    assert "session_id" in body
    assert any(c["type"] == "start_training" for c in body["available_commands"])


@pytest.mark.integration
def test_create_session_with_welcome_payload_starts_training(client: TestClient) -> None:
    res = client.post(
        "/api/sessions",
        json={"employee_name": "Анна", "product_id": "cc_novichok"},
    )

    assert res.status_code == 201
    body = res.json()
    assert body["state"] == "WELCOME"
    assert body["ctx"]["employee_name"] == "Анна"
    assert body["ctx"]["product_id"] == "cc_novichok"
    assert any(c["type"] == "select_mode" for c in body["available_commands"])
    assert any(e["type"] == "emit_text" for e in body["effects"])


@pytest.mark.integration
def test_create_session_emits_avatar_text(client: TestClient) -> None:
    """С Avatar в DI первый ответ содержит реплику аватара для MENU."""
    body = client.post("/api/sessions").json()
    text_effects = [e for e in body["effects"] if e["type"] == "emit_text"]
    assert text_effects, "ожидался EmitText от аватара"
    assert text_effects[0]["text"].strip()


@pytest.mark.integration
def test_create_session_no_audio_with_null_tts(client: TestClient) -> None:
    """NullTTS не должен порождать PlayAudio."""
    body = client.post("/api/sessions").json()
    assert not [e for e in body["effects"] if e["type"] == "play_audio"]


@pytest.mark.integration
def test_get_session_404(client: TestClient) -> None:
    res = client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


@pytest.mark.integration
def test_dispatch_unknown_session_404(client: TestClient) -> None:
    res = client.post(
        "/api/sessions/00000000-0000-0000-0000-000000000000/commands",
        json={"command": {"type": "start_training"}},
    )
    assert res.status_code == 404


@pytest.mark.integration
def test_full_training_flow(client: TestClient) -> None:
    sid = client.post("/api/sessions").json()["session_id"]

    res = client.post(
        f"/api/sessions/{sid}/commands",
        json={"command": {"type": "start_training"}},
    )
    assert res.status_code == 200
    assert res.json()["state"] == "WELCOME"

    res = client.post(
        f"/api/sessions/{sid}/commands",
        json={"command": {"type": "select_mode", "mode": "training"}},
    )
    assert res.json()["state"] == "TRAINING"

    res = client.post(
        f"/api/sessions/{sid}/commands",
        json={"command": {"type": "theory_done"}},
    )
    assert res.json()["state"] == "TRAINING_QUIZ"


@pytest.mark.integration
def test_invalid_command_for_state_returns_409(client: TestClient) -> None:
    sid = client.post("/api/sessions").json()["session_id"]
    res = client.post(
        f"/api/sessions/{sid}/commands",
        json={"command": {"type": "theory_done"}},
    )
    assert res.status_code == 409


@pytest.mark.integration
def test_unknown_command_type_returns_422(client: TestClient) -> None:
    sid = client.post("/api/sessions").json()["session_id"]
    res = client.post(
        f"/api/sessions/{sid}/commands",
        json={"command": {"type": "no_such_command"}},
    )
    assert res.status_code == 422


@pytest.mark.integration
def test_index_html_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "AI Tutor" in res.text


@pytest.mark.integration
def test_audio_endpoint_404_on_unknown_key(client: TestClient) -> None:
    res = client.get("/api/audio/deadbeef.wav")
    assert res.status_code == 404
