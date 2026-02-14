from huddle_chat.providers.gemini import GeminiClient


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
