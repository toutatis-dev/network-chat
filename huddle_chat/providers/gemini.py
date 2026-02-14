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
        try:
            data = post_json_request(url, {"x-goog-api-key": api_key}, payload)
        except RuntimeError as exc:
            # Compatibility fallback for deployments that still require query-key auth.
            message = str(exc).lower()
            if (
                "http 401" not in message and "http 403" not in message
            ) or "api key" not in message:
                raise
            fallback_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:"
                f"generateContent?key={api_key}"
            )
            data = post_json_request(fallback_url, {}, payload)
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
