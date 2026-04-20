import asyncio
import json

from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer
from google.genai import types

from mws_assistant import api


class FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str, str], dict] = {}

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> dict | None:
        return self.sessions.get((app_name, user_id, session_id))

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        state: dict,
    ) -> dict:
        session = {"state": state}
        self.sessions[(app_name, user_id, session_id)] = session
        return session


class FakeEvent:
    def __init__(
        self,
        *,
        text: str = "",
        partial: bool = False,
        final: bool = False,
        usage_metadata=None,
    ) -> None:
        self.content = types.Content(
            role="model",
            parts=[types.Part(text=text)],
        )
        self.partial = partial
        self.usage_metadata = usage_metadata
        self._final = final

    def is_final_response(self) -> bool:
        return self._final


class FakeRunner:
    def __init__(self, event_sequences: list[list[FakeEvent]]) -> None:
        self.event_sequences = event_sequences
        self.calls: list[dict] = []

    async def run_async(
        self,
        *,
        user_id: str,
        session_id: str,
        new_message: types.Content,
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "new_message": new_message,
            }
        )

        if self.event_sequences:
            events = self.event_sequences.pop(0)
        else:
            events = []

        for event in events:
            yield event


async def run_with_test_client(test_coro) -> None:
    client = TestClient(TestServer(api.create_app()))
    await client.start_server()
    try:
        await test_coro(client)
    finally:
        await client.close()


def test_health_endpoint_returns_ok() -> None:
    async def scenario(client: TestClient) -> None:
        response = await client.get("/health")
        assert response.status == 200
        assert await response.json() == {"status": "ok"}

    asyncio.run(run_with_test_client(scenario))


def test_models_endpoint_returns_public_model() -> None:
    async def scenario(client: TestClient) -> None:
        response = await client.get("/v1/models")
        body = await response.json()

        assert response.status == 200
        assert body["object"] == "list"
        assert body["data"][0]["id"] == api.PUBLIC_MODEL_NAME

    asyncio.run(run_with_test_client(scenario))


def test_chat_completions_rejects_invalid_json() -> None:
    async def scenario(client: TestClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            data="{bad json",
            headers={"Content-Type": "application/json"},
        )
        body = await response.json()

        assert response.status == 400
        assert body["error"]["type"] == "invalid_request_error"

    asyncio.run(run_with_test_client(scenario))


def test_chat_completions_returns_usage_and_session_header(monkeypatch) -> None:
    usage = SimpleNamespace(
        prompt_token_count=12,
        candidates_token_count=34,
        total_token_count=46,
    )
    fake_runner = FakeRunner(
        [
            [
                FakeEvent(
                    text="assistant answer",
                    final=True,
                    usage_metadata=usage,
                )
            ]
        ]
    )
    fake_sessions = FakeSessionService()

    monkeypatch.setattr(api, "RUNNER", fake_runner)
    monkeypatch.setattr(api, "SESSION_SERVICE", fake_sessions)

    async def scenario(client: TestClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": api.PUBLIC_MODEL_NAME,
                "messages": [
                    {"role": "user", "content": "hello"},
                ],
                "stream": False,
            },
        )
        body = await response.json()

        assert response.status == 200
        assert body["choices"][0]["message"]["content"] == "assistant answer"
        assert body["usage"] == {
            "prompt_tokens": 12,
            "completion_tokens": 34,
            "total_tokens": 46,
        }
        assert response.headers["X-Session-Id"].startswith("session-")

    asyncio.run(run_with_test_client(scenario))


def test_chat_completions_reuses_server_session(monkeypatch) -> None:
    usage = SimpleNamespace(
        prompt_token_count=5,
        candidates_token_count=6,
        total_token_count=11,
    )
    fake_runner = FakeRunner(
        [
            [FakeEvent(text="first answer", final=True, usage_metadata=usage)],
            [FakeEvent(text="second answer", final=True, usage_metadata=usage)],
        ]
    )
    fake_sessions = FakeSessionService()

    monkeypatch.setattr(api, "RUNNER", fake_runner)
    monkeypatch.setattr(api, "SESSION_SERVICE", fake_sessions)

    async def scenario(client: TestClient) -> None:
        first_response = await client.post(
            "/v1/chat/completions",
            json={
                "model": api.PUBLIC_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "seed"},
                    {"role": "user", "content": "first message"},
                ],
                "stream": False,
            },
        )
        session_id = first_response.headers["X-Session-Id"]

        second_response = await client.post(
            "/v1/chat/completions",
            json={
                "model": api.PUBLIC_MODEL_NAME,
                "messages": [
                    {"role": "user", "content": "second message"},
                ],
                "stream": False,
            },
            headers={"X-Session-Id": session_id},
        )

        assert first_response.status == 200
        assert second_response.status == 200
        assert fake_runner.calls[0]["session_id"] == session_id
        assert fake_runner.calls[1]["session_id"] == session_id
        assert fake_runner.calls[0]["new_message"].parts[0].text == "SYSTEM: seed\n\nUSER: first message"
        assert fake_runner.calls[1]["new_message"].parts[0].text == "second message"

    asyncio.run(run_with_test_client(scenario))


def test_chat_completions_stream_returns_sse_chunks(monkeypatch) -> None:
    fake_runner = FakeRunner(
        [
            [
                FakeEvent(text="streamed answer", final=True),
            ]
        ]
    )
    fake_sessions = FakeSessionService()

    monkeypatch.setattr(api, "RUNNER", fake_runner)
    monkeypatch.setattr(api, "SESSION_SERVICE", fake_sessions)

    async def scenario(client: TestClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": api.PUBLIC_MODEL_NAME,
                "messages": [
                    {"role": "user", "content": "hello"},
                ],
                "stream": True,
            },
        )
        body = await response.text()

        assert response.status == 200
        assert response.headers["Content-Type"].startswith("text/event-stream")
        assert "chat.completion.chunk" in body
        assert '"role": "assistant"' in body
        assert "streamed answer" in body
        assert "data: [DONE]" in body

    asyncio.run(run_with_test_client(scenario))
