# User Config API - Manual Testing Guide

This guide explains how to test the User Config API server manually.

## Prerequisites

1. Install the API server dependencies:
   ```bash
   cd user_config_api
   pip install -r requirements.txt
   ```

## Testing the API Server

### 1. Start the API Server

```bash
cd user_config_api
uvicorn server:app --host 0.0.0.0 --port 8080
```

### 2. Test Health Check Endpoint (No Authentication Required)

```bash
curl http://localhost:8080/health
```

Expected output:
```json
{"status":"ok"}
```

### 3. Test Config Endpoint with Correct Authentication

```bash
curl -H "Authorization: Bearer your-secret-api-key-here" \
  http://localhost:8080/config/github/notfolder | python -m json.tool
```

Expected output:
```json
{
    "status": "success",
    "data": {
        "llm": {
            "provider": "openai",
            ...
        },
        "system_prompt": "...",
        "max_llm_process_num": 1000
    }
}
```

### 4. Test Config Endpoint without Authentication (Should Fail)

```bash
curl http://localhost:8080/config/github/notfolder
```

Expected output (401 Unauthorized):
```json
{
    "detail": "認証に失敗しました"
}
```

### 5. Test Config Endpoint with Wrong API Key (Should Fail)

```bash
curl -H "Authorization: Bearer wrong-key" \
  http://localhost:8080/config/github/notfolder
```

Expected output (401 Unauthorized):
```json
{
    "detail": "認証に失敗しました"
}
```

## Testing the Integration with main.py

### 1. Start the API Server (as above)

### 2. Run a Test Script

Create a test script:

```python
import os
import requests
import yaml

# Set environment variables
os.environ["TASK_SOURCE"] = "github"
os.environ["USER_CONFIG_API_URL"] = "http://localhost:8080"
os.environ["USER_CONFIG_API_KEY"] = "your-secret-api-key-here"
os.environ["USE_USER_CONFIG_API"] = "true"

# Test config loading
# (This would require importing main.py with all dependencies installed)
```

## Testing with Docker Compose

### 1. Build and Start Services

```bash
docker-compose up --build user-config-api
```

### 2. Test from Inside Docker Network

```bash
# From another container in the same network
curl http://user-config-api:8080/health
```

## Environment Variables

- `API_SERVER_KEY`: API key for authentication (overrides config.yaml)
- `USE_USER_CONFIG_API`: Set to "true" to enable API-based config loading in main.py
- `USER_CONFIG_API_URL`: URL of the API server (default: http://user-config-api:8080)
- `USER_CONFIG_API_KEY`: API key for accessing the config API

## Manual Test Results

All tests passed successfully:
- ✓ Health check endpoint (no auth required)
- ✓ Config endpoint with correct Bearer token (200 OK)
- ✓ Config endpoint without authentication (401 Unauthorized)
- ✓ Config endpoint with wrong Bearer token (401 Unauthorized)
- ✓ Integration test with _fetch_config_from_api function
