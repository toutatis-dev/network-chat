import types
from unittest.mock import patch

from huddle_chat.providers.gemini import GeminiClient
from huddle_chat.providers.openai import OpenAIClient


def _response() -> dict:
    return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}


def test_gemini_uses_header_api_key_first():
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_post(url: str, headers: dict[str, str], payload: dict) -> dict:
        calls.append((url, headers))
        return _response()

    client = GeminiClient()
    text = client.generate(
        api_key="secret-key",
        model="gemini-2.5-flash",
        prompt="hi",
        post_json_request=fake_post,
    )
    assert text == "ok"
    assert len(calls) == 1
    assert "?key=" not in calls[0][0]
    assert calls[0][1] == {"x-goog-api-key": "secret-key"}


def test_gemini_does_not_fallback_to_query_key():
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_post(url: str, headers: dict[str, str], payload: dict) -> dict:
        calls.append((url, headers))
        raise RuntimeError("HTTP 403 from provider. API key invalid.")

    client = GeminiClient()
    try:
        client.generate(
            api_key="secret-key",
            model="gemini-2.5-flash",
            prompt="hi",
            post_json_request=fake_post,
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert "HTTP 403" in str(exc)
    assert len(calls) == 1
    assert "?key=secret-key" not in calls[0][0]


def test_openai_streaming_aggregates_chunks():
    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return [
                types.SimpleNamespace(
                    choices=[
                        types.SimpleNamespace(delta=types.SimpleNamespace(content="A"))
                    ]
                ),
                types.SimpleNamespace(
                    choices=[
                        types.SimpleNamespace(delta=types.SimpleNamespace(content="B"))
                    ]
                ),
            ]

    class FakeOpenAI:
        def __init__(self, api_key: str):
            assert api_key == "sk-openai"
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
    tokens: list[str] = []
    with patch.dict("sys.modules", {"openai": fake_module}):
        client = OpenAIClient()
        answer = client.generate_stream(
            api_key="sk-openai",
            model="gpt-4o-mini",
            prompt="hello",
            on_token=tokens.append,
        )
    assert answer == "AB"
    assert tokens == ["A", "B"]


def test_gemini_streaming_aggregates_chunks():
    class FakeModels:
        def generate_content_stream(self, model: str, contents: str):
            assert model == "gemini-2.5-flash"
            assert contents == "hello"
            return [types.SimpleNamespace(text="A"), types.SimpleNamespace(text="B")]

    class FakeClient:
        def __init__(self, api_key: str):
            assert api_key == "sk-gemini"
            self.models = FakeModels()

    fake_genai = types.SimpleNamespace(Client=FakeClient)
    fake_google = types.SimpleNamespace(genai=fake_genai)
    tokens: list[str] = []
    with patch.dict("sys.modules", {"google": fake_google, "google.genai": fake_genai}):
        client = GeminiClient()
        answer = client.generate_stream(
            api_key="sk-gemini",
            model="gemini-2.5-flash",
            prompt="hello",
            on_token=tokens.append,
        )
    assert answer == "AB"
    assert tokens == ["A", "B"]
