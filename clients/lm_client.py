from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .llm_base import LLMClient
from .lmstudio_client import LMStudioClient
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient


class LLMClient(ABC):
    @abstractmethod
    def send_system_prompt(self, prompt: str) -> None:
        pass

    @abstractmethod
    def send_user_message(self, message: str) -> None:
        pass

    @abstractmethod
    def send_function_result(self, name: str, result: Any) -> None:
        pass

    @abstractmethod
    def get_response(self) -> str:
        pass


def get_llm_client(
    config: dict[str, Any],
    functions: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> LLMClient:
    prov = config["llm"]["provider"]
    if prov == "lmstudio":
        if functions is not None:
            msg = "LMStudio does not support functions. use openapi compatible call."
            raise ValueError(msg)
        return LMStudioClient(config["llm"]["lmstudio"])
    if prov == "ollama":
        # TODO: functions support
        return OllamaClient(config["llm"]["ollama"])
    if prov == "openai":
        return OpenAIClient(config["llm"]["openai"], functions, tools)
    if prov == "mock":
        # Import here to avoid circular import during testing
        try:
            from tests.mocks.mock_llm_client import get_mock_llm_client

            return get_mock_llm_client(config, functions, tools)
        except ImportError:
            msg = "Mock LLM client not available - this should only be used in tests"
            raise ValueError(msg)
    else:
        msg = f"Unknown llm.provider: {prov}"
        raise ValueError(msg)
