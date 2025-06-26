from abc import ABC, abstractmethod

class Task(ABC):
    @abstractmethod
    def prepare(self):
        """タスクの準備処理（例: ラベル付けなど）"""
        pass

    @abstractmethod
    def get_prompt(self):
        """LLMに渡すプロンプトを生成"""
        pass

    @abstractmethod
    def comment(self, text, mention=False):
        """タスクにコメントを追加する。mention=Trueならownerにメンション"""
        pass

    @abstractmethod
    def finish(self):
        """タスクの完了処理（例: ラベル付け変更など）"""
        pass
