#!/usr/bin/env python3
"""
RabbitMQ connection test script
"""
import pika
import json
import sys
import os

def test_rabbitmq_connection():
    try:
        # RabbitMQ connection parameters
        host = os.getenv('RABBITMQ_HOST', 'localhost')
        port = int(os.getenv('RABBITMQ_PORT', '5672'))
        user = os.getenv('RABBITMQ_USER', 'guest')
        password = os.getenv('RABBITMQ_PASSWORD', 'guest')
        queue = os.getenv('RABBITMQ_QUEUE', 'mcp_tasks')
        
        print(f"Connecting to RabbitMQ at {host}:{port}")
        
        # Create connection
        credentials = pika.PlainCredentials(user, password)
        parameters = pika.ConnectionParameters(host=host, port=port, credentials=credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare queue
        channel.queue_declare(queue=queue, durable=True)
        print(f"✅ Successfully connected to RabbitMQ and declared queue '{queue}'")
        
        # Send test message
        test_message = {"test": "message", "timestamp": "2025-09-07"}
        channel.basic_publish(
            exchange='',
            routing_key=queue,
            body=json.dumps(test_message),
            properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
        )
        print("✅ Test message sent successfully")
        
        # Close connection
        connection.close()
        print("✅ RabbitMQ test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ RabbitMQ connection failed: {e}")
        return False

if __name__ == "__main__":
    success = test_rabbitmq_connection()
    sys.exit(0 if success else 1)
