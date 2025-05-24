import os
from typing import Dict, Any, Optional
import lmstudio as lms

class LMClient:
    def __init__(self, lm_config: Dict[str, Any]):
        self.model_name = lm_config.get('model', 'llama-3.2-1b-instruct')
        self.model = lms.llm(self.model_name)

    def chat(self, system_prompt: str, user_prompt: str, previous_output: Optional[str] = None, max_retries: int = 5) -> str:
        # lmstudio-pythonのAPIでsystem, user, assistantの会話履歴を渡す
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        if previous_output:
            messages.append({"role": "assistant", "content": previous_output})
        prompt = "\n".join([m["content"] for m in messages])
        for i in range(max_retries):
            try:
                result = self.model.respond(prompt)
                return result
            except Exception as e:
                if i == max_retries - 1:
                    raise
        return ""
