from abc import ABC, abstractmethod

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
