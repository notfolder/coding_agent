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

    @abstractmethod
    def check(self):
        """タスクの状態を確認する"""
        pass

    @abstractmethod
    def get_task_key(self):
        """タスクの一意なキーを取得"""
        pass
