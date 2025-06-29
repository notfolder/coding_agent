from abc import ABC, abstractmethod
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
    def send_function_result(self, name: str, result) -> None:
        pass

    @abstractmethod
    def get_response(self) -> str:
        pass

def get_llm_client(config, functions=None, tools=None) -> LLMClient:
    prov = config['llm']['provider']
    if prov == 'lmstudio':
        if functions is not None:
            raise ValueError("LMStudio does not support functions. use openapi compatible call.")
        return LMStudioClient(config['llm']['lmstudio'])
    elif prov == 'ollama':
        # Todo: functions support
        return OllamaClient(config['llm']['ollama'])
    elif prov == 'openai':
        return OpenAIClient(config['llm']['openai'], functions, tools)
    else:
        raise ValueError(f"Unknown llm.provider: {prov}")
