# Google Street View API Key Setup

This system automates the creation of 70 Google Cloud projects with API keys for high-throughput Street View image downloads.

## Prerequisites

1. **Google Cloud SDK (gcloud CLI)**
   - Download: https://cloud.google.com/sdk/docs/install
   - Or run: `winget install Google.CloudSDK` (Windows)

2. **Python 3.8+**

3. **A Google Account with billing enabled**

## Quick Start

### Step 1: Authenticate with Google Cloud

```bash
gcloud auth login
gcloud auth application-default login
```

### Step 2: Get your Billing Account ID

```bash
gcloud billing accounts list
```

Copy the `ACCOUNT_ID` (format: `XXXXXX-XXXXXX-XXXXXX`)

### Step 3: Configure the script

Edit `config.py` and set your billing account ID.

### Step 4: Run the automation

```bash
cd scripts/gsv_setup
pip install -r requirements.txt
python create_projects.py
```

### Step 5: Copy keys to Render

The script will output a comma-separated list of all API keys.
Copy this to your Render environment variable `GSV_API_KEYS`.

## Files

- `config.py` - Configuration (billing account, number of projects)
- `create_projects.py` - Main automation script
- `manage_keys.py` - View/manage existing keys
- `keys.json` - Generated keys storage (auto-created)

## Troubleshooting

### "Billing account not found"
- Ensure billing is enabled: https://console.cloud.google.com/billing

### "Quota exceeded for project creation"
- Google limits ~30 projects per account by default
- Request increase: https://console.cloud.google.com/iam-admin/quotas

### "API not enabled"
- The script auto-enables APIs, but you can manually enable at:
  https://console.cloud.google.com/apis/library/streetviewpublish.googleapis.com

