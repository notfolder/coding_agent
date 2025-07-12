import os
from abc import ABC, abstractmethod
from queue import Empty, Queue

import pika
import yaml


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


class RabbitMQTaskQueue(TaskQueue):
    def __init__(self, config):
        import pika

        mq_conf = config.get("rabbitmq", {})
        self.queue_name = mq_conf.get("queue", "coding_agent_tasks")
        self.host = mq_conf.get("host", "localhost")
        self.port = mq_conf.get("port", 5672)
        self.user = mq_conf.get("user", "guest")
        self.password = mq_conf.get("password", "guest")
        credentials = pika.PlainCredentials(self.user, self.password)
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=self.host, port=self.port, credentials=credentials),
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True)

    def put(self, task):
        import json

        body = json.dumps(task)
        self.channel.basic_publish(
            exchange="",
            routing_key=self.queue_name,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2),  # 永続化
        )

    def get(self, timeout=None):
        import json

        method_frame, header_frame, body = self.channel.basic_get(
            queue=self.queue_name, auto_ack=True,
        )
        if method_frame:
            return json.loads(body)
        return None

    def empty(self):
        q = self.channel.queue_declare(queue=self.queue_name, passive=True)
        return q.method.message_count == 0
