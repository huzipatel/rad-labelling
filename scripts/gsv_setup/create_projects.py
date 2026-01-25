#!/usr/bin/env python3
"""
Automated Google Cloud Project and API Key Creator

This script creates multiple Google Cloud projects with Street View API keys
for high-throughput image downloading.

Usage:
    1. Edit config.py with your billing account ID
    2. Run: python create_projects.py
    3. Copy the output keys to your GSV_API_KEYS environment variable
"""

import subprocess
import json
import time
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Import configuration
from config import (
    BILLING_ACCOUNT_ID,
    NUM_PROJECTS,
    PROJECT_PREFIX,
    ORGANIZATION_ID,
    APIS_TO_ENABLE,
    KEYS_OUTPUT_FILE,
    MAX_WORKERS,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
)


def run_command(cmd: list, capture_output: bool = True) -> tuple:
    """Run a gcloud command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=120
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_prerequisites():
    """Check if gcloud is installed and authenticated."""
    print("🔍 Checking prerequisites...")
    
    # Check gcloud installed
    success, output, _ = run_command(["gcloud", "version"])
    if not success:
        print("❌ gcloud CLI not found. Install it from: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)
    print("✅ gcloud CLI installed")
    
    # Check authenticated
    success, output, _ = run_command(["gcloud", "auth", "list", "--format=json"])
    if not success or "[]" in output:
        print("❌ Not authenticated. Run: gcloud auth login")
        sys.exit(1)
    print("✅ gcloud authenticated")
    
    # Check billing account
    if not BILLING_ACCOUNT_ID:
        print("❌ BILLING_ACCOUNT_ID not set in config.py")
        print("   Run: gcloud billing accounts list")
        print("   Then edit config.py with your billing account ID")
        sys.exit(1)
    
    success, output, _ = run_command([
        "gcloud", "billing", "accounts", "describe", BILLING_ACCOUNT_ID,
        "--format=json"
    ])
    if not success:
        print(f"❌ Billing account {BILLING_ACCOUNT_ID} not found or not accessible")
        sys.exit(1)
    print(f"✅ Billing account {BILLING_ACCOUNT_ID} verified")
    
    return True


def create_project(project_num: int) -> dict:
    """Create a single project with API key."""
    project_id = f"{PROJECT_PREFIX}-{project_num}"
    result = {
        "project_id": project_id,
        "project_num": project_num,
        "status": "pending",
        "api_key": None,
        "error": None
    }
    
    print(f"\n{'='*50}")
    print(f"📦 Creating project {project_num}/{NUM_PROJECTS}: {project_id}")
    print(f"{'='*50}")
    
    # Step 1: Create project
    for attempt in range(MAX_RETRIES):
        cmd = ["gcloud", "projects", "create", project_id, "--name", f"GSV Download {project_num}"]
        if ORGANIZATION_ID:
            cmd.extend(["--organization", ORGANIZATION_ID])
        
        success, output, error = run_command(cmd)
        
        if success:
            print(f"  ✅ Project created")
            break
        elif "already exists" in error.lower():
            print(f"  ⚠️ Project already exists, continuing...")
            break
        else:
            print(f"  ⚠️ Attempt {attempt + 1} failed: {error}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    else:
        result["status"] = "failed"
        result["error"] = f"Failed to create project: {error}"
        return result
    
    # Step 2: Link billing
    print(f"  💳 Linking billing account...")
    for attempt in range(MAX_RETRIES):
        success, output, error = run_command([
            "gcloud", "billing", "projects", "link", project_id,
            "--billing-account", BILLING_ACCOUNT_ID
        ])
        
        if success or "already linked" in error.lower():
            print(f"  ✅ Billing linked")
            break
        else:
            print(f"  ⚠️ Attempt {attempt + 1} failed: {error}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    else:
        result["status"] = "failed"
        result["error"] = f"Failed to link billing: {error}"
        return result
    
    # Step 3: Enable APIs
    print(f"  🔌 Enabling APIs...")
    for api in APIS_TO_ENABLE:
        for attempt in range(MAX_RETRIES):
            success, output, error = run_command([
                "gcloud", "services", "enable", api,
                "--project", project_id
            ])
            
            if success or "already enabled" in error.lower():
                print(f"    ✅ {api}")
                break
            else:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
        else:
            print(f"    ⚠️ Failed to enable {api}: {error}")
    
    # Step 4: Create API key
    print(f"  🔑 Creating API key...")
    for attempt in range(MAX_RETRIES):
        # First try the newer api-keys command
        success, output, error = run_command([
            "gcloud", "services", "api-keys", "create",
            "--project", project_id,
            "--display-name", f"GSV-Key-{project_num}",
            "--format=json"
        ])
        
        if success:
            try:
                # Try to parse the key from output
                key_data = json.loads(output)
                api_key = key_data.get("keyString") or key_data.get("key", {}).get("keyString")
                
                if api_key:
                    result["api_key"] = api_key
                    result["status"] = "success"
                    print(f"  ✅ API key created: {api_key[:10]}...")
                    return result
            except json.JSONDecodeError:
                pass
        
        # Fallback: Get key from console (newer gcloud versions)
        success, output, error = run_command([
            "gcloud", "services", "api-keys", "list",
            "--project", project_id,
            "--format=json"
        ])
        
        if success:
            try:
                keys = json.loads(output)
                if keys and len(keys) > 0:
                    # Get the key string
                    key_name = keys[0].get("name", "")
                    if key_name:
                        success, output, error = run_command([
                            "gcloud", "services", "api-keys", "get-key-string",
                            key_name,
                            "--format=json"
                        ])
                        if success:
                            key_data = json.loads(output)
                            api_key = key_data.get("keyString")
                            if api_key:
                                result["api_key"] = api_key
                                result["status"] = "success"
                                print(f"  ✅ API key retrieved: {api_key[:10]}...")
                                return result
            except (json.JSONDecodeError, IndexError, KeyError):
                pass
        
        print(f"  ⚠️ Attempt {attempt + 1} failed to get API key")
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY_SECONDS)
    
    # If we couldn't get the key automatically, mark for manual retrieval
    result["status"] = "needs_manual_key"
    result["error"] = "API key created but couldn't retrieve automatically"
    print(f"  ⚠️ Key created but needs manual retrieval from console")
    
    return result


def save_results(results: list):
    """Save results to JSON file."""
    output_path = Path(KEYS_OUTPUT_FILE)
    
    # Load existing results if any
    existing = []
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
        except:
            pass
    
    # Merge results (update existing, add new)
    existing_ids = {r["project_id"]: i for i, r in enumerate(existing)}
    
    for result in results:
        if result["project_id"] in existing_ids:
            existing[existing_ids[result["project_id"]]] = result
        else:
            existing.append(result)
    
    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2)
    
    print(f"\n💾 Results saved to {output_path}")


def main():
    """Main entry point."""
    print("=" * 60)
    print("🚀 GSV API Key Generator")
    print(f"   Creating {NUM_PROJECTS} projects with API keys")
    print("=" * 60)
    
    # Check prerequisites
    check_prerequisites()
    
    # Load existing results
    existing_results = []
    if Path(KEYS_OUTPUT_FILE).exists():
        try:
            with open(KEYS_OUTPUT_FILE) as f:
                existing_results = json.load(f)
            print(f"\n📂 Found {len(existing_results)} existing projects")
        except:
            pass
    
    # Determine which projects to create
    existing_ids = {r["project_id"] for r in existing_results if r.get("status") == "success"}
    projects_to_create = []
    
    for i in range(1, NUM_PROJECTS + 1):
        project_id = f"{PROJECT_PREFIX}-{i}"
        if project_id not in existing_ids:
            projects_to_create.append(i)
    
    if not projects_to_create:
        print("\n✅ All projects already created!")
    else:
        print(f"\n📝 Creating {len(projects_to_create)} new projects...")
        
        # Create projects (sequentially for reliability)
        results = existing_results.copy()
        
        for project_num in projects_to_create:
            result = create_project(project_num)
            results.append(result)
            
            # Save after each project (in case of interruption)
            save_results(results)
        
        existing_results = results
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    successful = [r for r in existing_results if r.get("status") == "success" and r.get("api_key")]
    failed = [r for r in existing_results if r.get("status") == "failed"]
    needs_manual = [r for r in existing_results if r.get("status") == "needs_manual_key"]
    
    print(f"  ✅ Successful: {len(successful)}")
    print(f"  ❌ Failed: {len(failed)}")
    print(f"  ⚠️ Need manual key: {len(needs_manual)}")
    
    if failed:
        print("\n❌ Failed projects:")
        for r in failed:
            print(f"   - {r['project_id']}: {r.get('error', 'Unknown error')}")
    
    if needs_manual:
        print("\n⚠️ Projects needing manual key retrieval:")
        for r in needs_manual:
            print(f"   - {r['project_id']}")
            print(f"     URL: https://console.cloud.google.com/apis/credentials?project={r['project_id']}")
    
    # Output all keys
    if successful:
        all_keys = [r["api_key"] for r in successful if r.get("api_key")]
        
        print("\n" + "=" * 60)
        print("🔑 ALL API KEYS (copy to GSV_API_KEYS in Render)")
        print("=" * 60)
        print(",".join(all_keys))
        
        # Also save to a separate file
        with open("api_keys.txt", "w") as f:
            f.write(",".join(all_keys))
        print(f"\n💾 Keys also saved to api_keys.txt")
        
        print(f"\n📈 With {len(all_keys)} keys, you can download ~{len(all_keys) * 25000:,} images/day")
        print(f"   At 1.73M total images, this will take ~{1730000 / (len(all_keys) * 25000):.1f} days")


if __name__ == "__main__":
    main()

