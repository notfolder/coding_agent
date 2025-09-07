#!/usr/bin/env bash

# Test mode - Mock tasks instead of real API calls
export GITHUB_PERSONAL_ACCESS_TOKEN="mock_token_for_testing"
export GITLAB_PERSONAL_ACCESS_TOKEN="mock_token_for_testing"
export TASK_SOURCE="mock"
export DEBUG="true"
export RABBITMQ_HOST="rabbitmq"
export RABBITMQ_PORT="5672"
export RABBITMQ_USER="guest"
export RABBITMQ_PASSWORD="guest"
export RABBITMQ_QUEUE="mcp_tasks"

echo "Starting with mock configuration for testing..."
echo "TASK_SOURCE: $TASK_SOURCE"
echo "RabbitMQ Host: $RABBITMQ_HOST"

# Use conda to run the application
source /opt/conda/etc/profile.d/conda.sh
conda activate coding-agent
python -u main.py
