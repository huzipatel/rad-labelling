#!/usr/bin/env python3
"""
Manage existing GSV API keys

Commands:
    python manage_keys.py list          - List all projects and keys
    python manage_keys.py export        - Export keys as comma-separated string
    python manage_keys.py refresh       - Refresh keys from Google Cloud
    python manage_keys.py delete-all    - Delete all created projects (careful!)
"""

import subprocess
import json
import sys
from pathlib import Path

from config import PROJECT_PREFIX, NUM_PROJECTS, KEYS_OUTPUT_FILE


def run_command(cmd: list) -> tuple:
    """Run a gcloud command and return (success, output, error)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def list_keys():
    """List all projects and their keys."""
    if not Path(KEYS_OUTPUT_FILE).exists():
        print("No keys.json found. Run create_projects.py first.")
        return
    
    with open(KEYS_OUTPUT_FILE) as f:
        results = json.load(f)
    
    print(f"\n{'Project ID':<25} {'Status':<15} {'API Key'}")
    print("-" * 80)
    
    for r in results:
        key_display = r.get("api_key", "N/A")
        if key_display and len(key_display) > 20:
            key_display = key_display[:20] + "..."
        
        status = r.get("status", "unknown")
        status_emoji = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
        
        print(f"{r['project_id']:<25} {status_emoji} {status:<12} {key_display}")
    
    # Summary
    successful = len([r for r in results if r.get("status") == "success"])
    print(f"\nTotal: {len(results)} projects, {successful} with valid keys")


def export_keys():
    """Export all keys as comma-separated string."""
    if not Path(KEYS_OUTPUT_FILE).exists():
        print("No keys.json found. Run create_projects.py first.")
        return
    
    with open(KEYS_OUTPUT_FILE) as f:
        results = json.load(f)
    
    keys = [r["api_key"] for r in results if r.get("api_key")]
    
    if keys:
        output = ",".join(keys)
        print("\n" + "=" * 60)
        print("GSV_API_KEYS value (copy this to Render):")
        print("=" * 60)
        print(output)
        
        # Save to file
        with open("api_keys.txt", "w") as f:
            f.write(output)
        print(f"\nAlso saved to api_keys.txt")
        print(f"\nTotal: {len(keys)} keys")
    else:
        print("No valid API keys found.")


def refresh_keys():
    """Refresh key values from Google Cloud."""
    print("Refreshing keys from Google Cloud...")
    
    if not Path(KEYS_OUTPUT_FILE).exists():
        results = []
    else:
        with open(KEYS_OUTPUT_FILE) as f:
            results = json.load(f)
    
    # Build project ID to result mapping
    results_map = {r["project_id"]: r for r in results}
    
    updated = 0
    for i in range(1, NUM_PROJECTS + 1):
        project_id = f"{PROJECT_PREFIX}-{i}"
        print(f"  Checking {project_id}...", end=" ")
        
        # List keys for this project
        success, output, error = run_command([
            "gcloud", "services", "api-keys", "list",
            "--project", project_id,
            "--format=json"
        ])
        
        if not success:
            print("❌ (project not found or no access)")
            continue
        
        try:
            keys = json.loads(output)
            if keys:
                key_name = keys[0].get("name", "")
                if key_name:
                    # Get key string
                    success, output, error = run_command([
                        "gcloud", "services", "api-keys", "get-key-string",
                        key_name,
                        "--format=json"
                    ])
                    
                    if success:
                        key_data = json.loads(output)
                        api_key = key_data.get("keyString")
                        
                        if api_key:
                            if project_id in results_map:
                                if results_map[project_id].get("api_key") != api_key:
                                    results_map[project_id]["api_key"] = api_key
                                    results_map[project_id]["status"] = "success"
                                    updated += 1
                                    print(f"✅ Updated: {api_key[:10]}...")
                                else:
                                    print("✅ (unchanged)")
                            else:
                                results_map[project_id] = {
                                    "project_id": project_id,
                                    "project_num": i,
                                    "status": "success",
                                    "api_key": api_key
                                }
                                updated += 1
                                print(f"✅ Found: {api_key[:10]}...")
                            continue
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
        
        print("⚠️ (no key found)")
    
    # Save results
    with open(KEYS_OUTPUT_FILE, "w") as f:
        json.dump(list(results_map.values()), f, indent=2)
    
    print(f"\n✅ Refreshed {updated} keys")


def delete_all_projects():
    """Delete all created projects (careful!)."""
    confirm = input(f"⚠️  This will DELETE all {NUM_PROJECTS} projects. Type 'DELETE' to confirm: ")
    
    if confirm != "DELETE":
        print("Cancelled.")
        return
    
    print("\nDeleting projects...")
    
    deleted = 0
    for i in range(1, NUM_PROJECTS + 1):
        project_id = f"{PROJECT_PREFIX}-{i}"
        print(f"  Deleting {project_id}...", end=" ")
        
        success, output, error = run_command([
            "gcloud", "projects", "delete", project_id, "--quiet"
        ])
        
        if success:
            deleted += 1
            print("✅")
        else:
            print(f"❌ ({error.strip()})")
    
    print(f"\n✅ Deleted {deleted} projects")
    
    # Remove local keys file
    if Path(KEYS_OUTPUT_FILE).exists():
        Path(KEYS_OUTPUT_FILE).unlink()
        print("Removed keys.json")


def show_usage():
    """Show usage information."""
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        show_usage()
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_keys()
    elif command == "export":
        export_keys()
    elif command == "refresh":
        refresh_keys()
    elif command == "delete-all":
        delete_all_projects()
    else:
        show_usage()


if __name__ == "__main__":
    main()

