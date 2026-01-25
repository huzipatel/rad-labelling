"""
Configuration for GSV API Key Setup

Edit this file before running create_projects.py
"""

# Your Google Cloud billing account ID
# Find it with: gcloud billing accounts list
# Format: XXXXXX-XXXXXX-XXXXXX
BILLING_ACCOUNT_ID = ""  # <-- SET THIS!

# Number of projects to create (max ~70 for 1.7M images in a day)
NUM_PROJECTS = 70

# Project naming
PROJECT_PREFIX = "gsv-download"  # Projects will be named gsv-download-1, gsv-download-2, etc.

# Organization ID (optional - leave empty if not using an organization)
ORGANIZATION_ID = ""

# APIs to enable on each project
APIS_TO_ENABLE = [
    "streetviewpublish.googleapis.com",  # Street View Publish API
    "places.googleapis.com",              # Places API (backup)
]

# Output file for generated keys
KEYS_OUTPUT_FILE = "keys.json"

# Parallel workers for faster creation
MAX_WORKERS = 5

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

