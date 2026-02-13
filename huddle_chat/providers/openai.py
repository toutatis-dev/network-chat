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
