from abc import ABC, abstractmethod
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
    def get_response(self) -> str:
        pass

def get_llm_client(config):
    prov = config['llm']['provider']
    if prov == 'lmstudio':
        return LMStudioClient(config['llm']['lmstudio'])
    elif prov == 'ollama':
        return OllamaClient(config['llm']['ollama'])
    elif prov == 'openai':
        return OpenAIClient(config['llm']['openai'])
    else:
        raise ValueError(f"Unknown llm.provider: {prov}")
