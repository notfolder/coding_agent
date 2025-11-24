from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .lmstudio_client import LMStudioClient
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient

# Conditional import for mock client to avoid circular imports in testing
try:
    from tests.mocks.mock_llm_client import get_mock_llm_client
except ImportError:
    get_mock_llm_client = None


class LLMClient(ABC):
    @abstractmethod
    def send_system_prompt(self, prompt: str) -> None:
        pass

    @abstractmethod
    def send_user_message(self, message: str) -> None:
        pass

    @abstractmethod
    def send_function_result(self, name: str, result: object) -> None:
        pass

    @abstractmethod
    def get_response(self) -> tuple[str, list]:
        pass


def get_llm_client(
    config: dict[str, Any],
    functions: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    message_store: Any = None,
    context_dir: Any = None,
) -> LLMClient:
    prov = config["llm"]["provider"]
    if prov == "lmstudio":
        if functions is not None:
            msg = "LMStudio does not support functions. use openapi compatible call."
            raise ValueError(msg)
        return LMStudioClient(config["llm"]["lmstudio"], message_store, context_dir)
    if prov == "ollama":
        return OllamaClient(config["llm"]["ollama"], message_store, context_dir)
    if prov == "openai":
        return OpenAIClient(config["llm"]["openai"], functions, tools, message_store, context_dir)
    if prov == "mock":
        if get_mock_llm_client is None:
            msg = "Mock LLM client not available - this should only be used in tests"
            raise ValueError(msg)
        return get_mock_llm_client(config, functions, tools)
    msg = f"Unknown llm.provider: {prov}"
    raise ValueError(msg)
