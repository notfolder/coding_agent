from abc import ABC, abstractmethod
from queue import Queue, Empty

class TaskQueue(ABC):
    @abstractmethod
    def put(self, task):
        pass

    @abstractmethod
    def get(self, timeout=None):
        pass

    @abstractmethod
    def empty(self):
        pass

class InMemoryTaskQueue(TaskQueue):
    def __init__(self):
        self.queue = Queue()
    def put(self, task):
        self.queue.put(task)
    def get(self, timeout=None):
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None
    def empty(self):
        return self.queue.empty()
