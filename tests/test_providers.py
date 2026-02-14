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


def test_gemini_falls_back_to_query_key_on_auth_failure():
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_post(url: str, headers: dict[str, str], payload: dict) -> dict:
        calls.append((url, headers))
        if len(calls) == 1:
            raise RuntimeError("HTTP 403 from provider. API key invalid.")
        return _response()

    client = GeminiClient()
    text = client.generate(
        api_key="secret-key",
        model="gemini-2.5-flash",
        prompt="hi",
        post_json_request=fake_post,
    )
    assert text == "ok"
    assert len(calls) == 2
    assert "?key=secret-key" in calls[1][0]
    assert calls[1][1] == {}
