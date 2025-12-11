# Claude Code Setup Guide

## Installation

Claude Code is installed via npm as `@anthropic-ai/claude-code`.

## Setup Options

### Option 1: Direct Anthropic API (Recommended for development)

The simplest way to get started with Claude Code.

**Setup:**
1. Get your API key from: https://console.anthropic.com/
2. Set the environment variable:
   ```bash
   export ANTHROPIC_API_KEY='your-api-key'
   ```
3. Add to your shell profile (~/.bashrc, ~/.zshrc, etc.) to persist

**Usage:**
```bash
claude-code --help           # Show help
claude-code <prompt>         # Run Claude Code with a prompt
```

### Option 2: Google Cloud Vertex AI (Recommended for production/enterprise)

Vertex AI provides access to Claude models via Google Cloud Platform.

**Prerequisites:**
- Google Cloud account with billing enabled
- A GCP project created
- Google Cloud SDK (gcloud) installed

**Setup Steps:**

1. **Install Google Cloud SDK** (if not already installed):
   - macOS: `brew install google-cloud-sdk`
   - Linux: `curl https://sdk.cloud.google.com | bash`

2. **Initialize and authenticate:**
   ```bash
   gcloud init
   gcloud auth login
   gcloud auth application-default login
   ```

3. **Set your project:**
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```

4. **Enable required APIs:**
   ```bash
   gcloud services enable aiplatform.googleapis.com
   ```

5. **Grant necessary permissions** (if needed):
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member='user:YOUR_EMAIL' \
     --role='roles/aiplatform.user'
   ```

6. **Set environment variables:**
   ```bash
   export GOOGLE_CLOUD_PROJECT='YOUR_PROJECT_ID'
   export GOOGLE_CLOUD_REGION='us-central1'  # or your preferred region
   ```

7. **Configure Claude Code to use Vertex AI:**
   Add to your shell profile (~/.bashrc, ~/.zshrc, etc.):
   ```bash
   export ANTHROPIC_VERTEX_AI=true
   export ANTHROPIC_PROJECT_ID='YOUR_PROJECT_ID'
   export ANTHROPIC_REGION='us-central1'
   ```

**Available Claude Models on Vertex AI:**
- `claude-3-opus@20240229`
- `claude-3-sonnet@20240229`
- `claude-3-haiku@20240307`
- `claude-3-5-sonnet@20240620`

**Vertex AI Benefits:**
- Enterprise-grade security and compliance
- Integrated with Google Cloud services
- Unified billing and management
- Data residency and privacy controls
- No separate Anthropic API key needed

## Interactive Setup

Run the installer with the `--setup-vertex-ai` flag for an interactive Vertex AI configuration:
```bash
./bin/claude/install --setup-vertex-ai
```

## More Information

- Vertex AI: https://cloud.google.com/vertex-ai/docs/generative-ai/model-garden/claude
- Anthropic: https://console.anthropic.com/
