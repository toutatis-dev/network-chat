from collections.abc import Callable
from typing import Any


class OpenAIClient:
    def generate(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        post_json_request: Any,
    ) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        data = post_json_request(url, headers, payload)
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI returned no choices.")
        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("OpenAI response format was invalid.")
        message = first.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("OpenAI response message missing.")
        text = str(message.get("content", "")).strip()
        if not text:
            raise RuntimeError("OpenAI response was empty.")
        return text

    def generate_stream(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        on_token: Callable[[str], None],
    ) -> str:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError(
                "OpenAI streaming requires the 'openai' package."
            ) from exc

        client = OpenAI(api_key=api_key)
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        chunks: list[str] = []
        for event in stream:
            choices = getattr(event, "choices", None)
            if not isinstance(choices, list) or not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                chunks.append(content)
                on_token(content)
        text = "".join(chunks).strip()
        if not text:
            raise RuntimeError("OpenAI response was empty.")
        return text
