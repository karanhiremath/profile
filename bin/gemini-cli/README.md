# Gemini CLI Setup Guide

## Installation

Gemini CLI is installed via pip as `gemini-cli`.

## Setup Options

### Option 1: Google AI Studio API (Recommended for development/personal use)

The simplest way to get started with Gemini.

**Setup:**
1. Get your API key from: https://makersuite.google.com/app/apikey
2. Set the environment variable:
   ```bash
   export GEMINI_API_KEY='your-api-key-here'
   ```
3. Add to your shell profile (~/.bashrc, ~/.zshrc, etc.) to persist

**Usage:**
```bash
gemini 'your prompt here'
```

### Option 2: Google Cloud Vertex AI (Recommended for production/enterprise)

Vertex AI provides native access to Gemini models via Google Cloud Platform.

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

7. **Using Vertex AI with Python SDK:**
   
   Install the Vertex AI SDK:
   ```bash
   pip3 install --user google-cloud-aiplatform
   ```
   
   Example usage in Python:
   ```python
   from google.cloud import aiplatform
   aiplatform.init(project='YOUR_PROJECT_ID', location='us-central1')
   ```

8. **Using gcloud CLI directly with Vertex AI:**
   
   Example curl command to generate content:
   ```bash
   curl -X POST \
     -H "Authorization: Bearer $(gcloud auth print-access-token)" \
     -H "Content-Type: application/json" \
     https://${GOOGLE_CLOUD_REGION}-aiplatform.googleapis.com/v1/projects/${GOOGLE_CLOUD_PROJECT}/locations/${GOOGLE_CLOUD_REGION}/publishers/google/models/gemini-pro:generateContent \
     -d '{"contents": [{"role": "user", "parts": [{"text": "Your prompt here"}]}]}'
   ```

**Available Gemini Models on Vertex AI:**
- `gemini-1.0-pro`
- `gemini-1.0-pro-vision`
- `gemini-1.5-pro`
- `gemini-1.5-flash`
- `gemini-2.0-flash-exp` (experimental)

**Vertex AI Benefits:**
- Enterprise-grade security and compliance
- Integrated with Google Cloud services
- Unified billing and management
- Higher rate limits and quotas
- Data residency and privacy controls
- Advanced features (grounding, function calling, etc.)

## Interactive Setup

Run the installer with the `--setup-vertex-ai` flag for an interactive Vertex AI configuration:
```bash
./bin/gemini-cli/install --setup-vertex-ai
```

## More Information

- Vertex AI: https://cloud.google.com/vertex-ai/docs/generative-ai/start/quickstarts/quickstart-multimodal
- Google AI Studio: https://makersuite.google.com/
- Gemini API: https://ai.google.dev/
