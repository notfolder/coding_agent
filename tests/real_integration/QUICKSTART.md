# Quick Start Guide: Real Integration Tests

This is a quick guide to get the real integration tests running.

## TL;DR - Quick Setup

1. **Set up test repository:**
   ```bash
   # Create a GitHub repository (e.g., myuser/coding-agent-test)
   # Get a GitHub token with 'repo' permissions
   ```

2. **Configure environment:**
   ```bash
   export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here"
   export GITHUB_TEST_REPO="myuser/coding-agent-test"
   export OPENAI_API_KEY="sk_your_openai_key_here"
   # Optional: For local LLM via OpenAI-compatible API
   export OPENAI_BASE_URL="http://localhost:1234/v1"
   export OPENAI_MODEL="your-model-name"
   ```

3. **Check configuration:**
   ```bash
   python tests/real_integration/check_config.py
   ```

4. **Run tests:**
   ```bash
   python tests/run_tests.py --real
   ```

## Expected Results

The tests will:
1. ✅ Create a `hello_world.py` file that prints "hello world"
2. ✅ Create a pull request modifying it for iris classification
3. ✅ Update the file to evaluate multiple ML models

## Test Scenarios

### Scenario 1: Hello World Creation
- **Input**: Japanese issue asking to create `hello_world.py`
- **Expected**: File created, executes correctly, prints "hello world"
- **Time**: ~3-5 minutes

### Scenario 2: Pull Request Creation
- **Input**: Japanese issue asking to add scikit-learn iris classification
- **Expected**: Branch created, pull request opened with modifications
- **Time**: ~5-7 minutes

### Scenario 3: PR Comment Processing
- **Input**: Comment asking for multiple model evaluation
- **Expected**: File updated with accuracy and confusion matrix code
- **Time**: ~3-5 minutes

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `GITHUB_PERSONAL_ACCESS_TOKEN not set` | Export your GitHub token |
| `Repository not found` | Check repository exists and token has access |
| `OpenAI API error` | Verify your OpenAI API key is valid |
| `Tests timeout` | Increase timeout or check repository activity |
| `File not created` | Check coding agent logs for errors |

## What Gets Created

In your test repository:
- `hello_world.py` - Python file with main function
- Issue(s) with coding agent labels
- Branch(es) for pull requests
- Pull request(s) with code changes
- Comments and status updates

## Cost Considerations

- **GitHub API**: Free for public repos, limited for private
- **OpenAI API**: ~$0.01-0.10 per test run (varies by model)
- **Time**: 10-15 minutes total test runtime

## Alternative Configurations

### GitLab Instead of GitHub
```bash
export GITLAB_PERSONAL_ACCESS_TOKEN="glpat_your_token_here"
export GITLAB_TEST_PROJECT="123"  # or "myuser/project"
export OPENAI_API_KEY="sk_your_openai_key_here"
```

### Different LLM Provider
```bash
# For LM Studio
export LLM_PROVIDER="lmstudio"
export LMSTUDIO_BASE_URL="http://localhost:1234"
export LMSTUDIO_MODEL="your-model"

# For Ollama  
export LLM_PROVIDER="ollama"
export OLLAMA_ENDPOINT="http://localhost:11434"
export OLLAMA_MODEL="your-model"
```

## For CI/CD

```yaml
# GitHub Actions example
env:
  GITHUB_PERSONAL_ACCESS_TOKEN: ${{ secrets.GITHUB_PERSONAL_ACCESS_TOKEN }}
  GITHUB_TEST_REPO: "myuser/test-repo"
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

steps:
  - run: python tests/run_tests.py --real
```

## Questions?

- 📖 Full documentation: `tests/real_integration/README.md`
- 🚀 Step-by-step demo: `python tests/real_integration/demo.py`
- ⚙️ Configuration check: `python tests/real_integration/check_config.py`