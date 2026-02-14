from collections.abc import Callable
from typing import Any, Protocol


class ProviderClient(Protocol):
    def generate(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        post_json_request: Any,
    ) -> str:
        pass

    def generate_stream(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        on_token: Callable[[str], None],
    ) -> str:
        pass
