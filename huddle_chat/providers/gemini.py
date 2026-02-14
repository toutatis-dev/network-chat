from collections.abc import Callable
from typing import Any


class GeminiClient:
    def generate(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        post_json_request: Any,
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = post_json_request(url, {"x-goog-api-key": api_key}, payload)
        candidates = data.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError("Gemini returned no candidates.")
        first = candidates[0]
        if not isinstance(first, dict):
            raise RuntimeError("Gemini response format was invalid.")
        content = first.get("content", {})
        if not isinstance(content, dict):
            raise RuntimeError("Gemini response content missing.")
        parts = content.get("parts", [])
        if not isinstance(parts, list) or not parts:
            raise RuntimeError("Gemini returned empty content.")
        for part in parts:
            if isinstance(part, dict):
                text = str(part.get("text", "")).strip()
                if text:
                    return text
        raise RuntimeError("Gemini response did not contain text.")

    def generate_stream(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        on_token: Callable[[str], None],
    ) -> str:
        try:
            from google import genai  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError(
                "Gemini streaming requires the 'google-genai' package."
            ) from exc

        client = genai.Client(api_key=api_key)
        chunks: list[str] = []
        stream = client.models.generate_content_stream(model=model, contents=prompt)
        for chunk in stream:
            text = getattr(chunk, "text", "")
            if isinstance(text, str) and text:
                chunks.append(text)
                on_token(text)
        answer = "".join(chunks).strip()
        if not answer:
            raise RuntimeError("Gemini response was empty.")
        return answer
