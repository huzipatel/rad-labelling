"""Admin routes for system management and reporting."""
import uuid
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.task import Task
from app.models.label import Label
from app.api.deps import require_manager, require_admin


router = APIRouter(prefix="/admin", tags=["Admin"])


class LabelerPerformance(BaseModel):
    """Labeller performance metrics."""
    user_id: str
    name: str
    email: str
    total_locations_labelled: int
    total_tasks_completed: int
    average_speed_per_hour: float
    failure_rate: float
    hourly_rate: Optional[float]
    cost_per_location: Optional[float]
    total_time_hours: float
    speed_rag: str
    failure_rag: str
    overall_rag: str


class PerformanceReport(BaseModel):
    """Performance report response."""
    labellers: List[LabelerPerformance]
    total_locations_labelled: int
    total_tasks_completed: int
    average_speed: float


class SystemStats(BaseModel):
    """System statistics."""
    total_users: int
    total_labellers: int
    total_managers: int
    total_locations: int
    total_tasks: int
    tasks_in_progress: int
    tasks_completed: int


def calculate_rag_status(metric: str, value: float) -> str:
    """Calculate RAG status for a metric."""
    thresholds = {
        "speed": {"green": 20, "amber": 10},  # locations/hour
        "failure_rate": {"green": 0.05, "amber": 0.15},  # percentage
        "completion": {"green": 0.9, "amber": 0.7}  # percentage
    }
    
    t = thresholds.get(metric, {"green": 0.8, "amber": 0.5})
    
    if metric == "failure_rate":
        if value <= t["green"]:
            return "green"
        elif value <= t["amber"]:
            return "amber"
        return "red"
    else:
        if value >= t["green"]:
            return "green"
        elif value >= t["amber"]:
            return "amber"
        return "red"


@router.get("/performance", response_model=PerformanceReport)
async def get_performance_report(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get performance report for all labellers."""
    since = datetime.utcnow() - timedelta(days=days)
    
    # Get all labellers
    labellers_result = await db.execute(
        select(User).where(User.role.in_(["labeller", "labelling_manager"]))
    )
    labellers = labellers_result.scalars().all()
    
    performance_data = []
    total_locations = 0
    total_tasks = 0
    
    for labeller in labellers:
        # Get labels by this labeller
        labels_result = await db.execute(
            select(Label).where(
                Label.labeller_id == labeller.id,
                Label.labelling_completed_at >= since
            )
        )
        labels = labels_result.scalars().all()
        
        # Get completed tasks
        tasks_result = await db.execute(
            select(Task).where(
                Task.assigned_to == labeller.id,
                Task.status == "completed",
                Task.completed_at >= since
            )
        )
        tasks = tasks_result.scalars().all()
        
        # Calculate metrics
        total_labelled = len(labels)
        failed = sum(1 for l in labels if l.unable_to_label)
        
        # Calculate total time
        total_time_seconds = sum(
            l.labelling_duration_seconds or 0
            for l in labels
            if l.labelling_duration_seconds
        )
        total_time_hours = total_time_seconds / 3600 if total_time_seconds > 0 else 0
        
        # Calculate speed
        speed = total_labelled / total_time_hours if total_time_hours > 0 else 0
        
        # Calculate failure rate
        failure_rate = failed / total_labelled if total_labelled > 0 else 0
        
        # Calculate cost
        hourly_rate = float(labeller.hourly_rate) if labeller.hourly_rate else None
        cost_per_location = None
        if hourly_rate and total_labelled > 0 and total_time_hours > 0:
            total_cost = hourly_rate * total_time_hours
            cost_per_location = total_cost / total_labelled
        
        # Calculate RAG status
        speed_rag = calculate_rag_status("speed", speed)
        failure_rag = calculate_rag_status("failure_rate", failure_rate)
        
        # Overall RAG
        rag_scores = {"green": 3, "amber": 2, "red": 1}
        avg_score = (rag_scores[speed_rag] + rag_scores[failure_rag]) / 2
        if avg_score >= 2.5:
            overall_rag = "green"
        elif avg_score >= 1.5:
            overall_rag = "amber"
        else:
            overall_rag = "red"
        
        performance_data.append(LabelerPerformance(
            user_id=str(labeller.id),
            name=labeller.name,
            email=labeller.email,
            total_locations_labelled=total_labelled,
            total_tasks_completed=len(tasks),
            average_speed_per_hour=round(speed, 2),
            failure_rate=round(failure_rate, 4),
            hourly_rate=hourly_rate,
            cost_per_location=round(cost_per_location, 2) if cost_per_location else None,
            total_time_hours=round(total_time_hours, 2),
            speed_rag=speed_rag,
            failure_rag=failure_rag,
            overall_rag=overall_rag
        ))
        
        total_locations += total_labelled
        total_tasks += len(tasks)
    
    # Sort by total labelled
    performance_data.sort(key=lambda x: x.total_locations_labelled, reverse=True)
    
    # Calculate overall average speed
    total_time = sum(p.total_time_hours for p in performance_data)
    avg_speed = total_locations / total_time if total_time > 0 else 0
    
    return PerformanceReport(
        labellers=performance_data,
        total_locations_labelled=total_locations,
        total_tasks_completed=total_tasks,
        average_speed=round(avg_speed, 2)
    )


@router.get("/labeller/{labeller_id}/view")
async def get_labeller_view(
    labeller_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get a labeller's current view for remote assistance."""
    # Get labeller
    labeller_result = await db.execute(
        select(User).where(User.id == labeller_id)
    )
    labeller = labeller_result.scalar_one_or_none()
    
    if not labeller:
        raise HTTPException(status_code=404, detail="Labeller not found")
    
    # Get active task
    task_result = await db.execute(
        select(Task).where(
            Task.assigned_to == labeller_id,
            Task.status == "in_progress"
        )
    )
    active_task = task_result.scalar_one_or_none()
    
    if not active_task:
        return {
            "labeller": {
                "id": str(labeller.id),
                "name": labeller.name,
                "email": labeller.email
            },
            "active_task": None,
            "current_location": None
        }
    
    # Get most recent label to find current location
    label_result = await db.execute(
        select(Label)
        .where(Label.task_id == active_task.id)
        .order_by(Label.updated_at.desc())
        .limit(1)
    )
    recent_label = label_result.scalar_one_or_none()
    
    return {
        "labeller": {
            "id": str(labeller.id),
            "name": labeller.name,
            "email": labeller.email
        },
        "active_task": {
            "id": str(active_task.id),
            "location_type": active_task.location_type.display_name,
            "council": active_task.council,
            "progress": active_task.completion_percentage,
            "completed": active_task.completed_locations,
            "total": active_task.total_locations
        },
        "current_location": {
            "id": str(recent_label.location_id),
            "identifier": recent_label.location.identifier if recent_label else None
        } if recent_label else None
    }


@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get system-wide statistics."""
    from app.models.location import Location
    
    # Count users by role
    users_result = await db.execute(
        select(User.role, func.count(User.id))
        .group_by(User.role)
    )
    user_counts = {role: count for role, count in users_result.all()}
    
    # Count locations
    locations_count = await db.execute(select(func.count(Location.id)))
    
    # Count tasks by status
    tasks_result = await db.execute(
        select(Task.status, func.count(Task.id))
        .group_by(Task.status)
    )
    task_counts = {status: count for status, count in tasks_result.all()}
    
    return SystemStats(
        total_users=sum(user_counts.values()),
        total_labellers=user_counts.get("labeller", 0),
        total_managers=user_counts.get("labelling_manager", 0),
        total_locations=locations_count.scalar(),
        total_tasks=sum(task_counts.values()),
        tasks_in_progress=task_counts.get("in_progress", 0),
        tasks_completed=task_counts.get("completed", 0)
    )


@router.post("/notify-managers")
async def notify_managers(
    message: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Send a notification to all managers via WhatsApp."""
    from app.services.whatsapp_notifier import WhatsAppNotifier
    
    # Get managers with WhatsApp numbers
    managers_result = await db.execute(
        select(User).where(
            User.role.in_(["labelling_manager", "admin"]),
            User.whatsapp_number.isnot(None)
        )
    )
    managers = managers_result.scalars().all()
    
    notifier = WhatsAppNotifier()
    sent_count = 0
    
    for manager in managers:
        try:
            await notifier.send_message(manager.whatsapp_number, message)
            sent_count += 1
        except Exception as e:
            print(f"Failed to notify {manager.email}: {e}")
    
    return {
        "message": f"Notification sent to {sent_count} managers",
        "sent_count": sent_count
    }


@router.get("/gsv-keys-status")
async def gsv_keys_status(
    current_user: User = Depends(require_admin)
):
    """Get status of all GSV API keys including usage and rate limit status."""
    from app.services.gsv_key_manager import gsv_key_manager
    
    return gsv_key_manager.get_status()


@router.post("/gsv-keys-reset/{key_prefix}")
async def reset_gsv_key(
    key_prefix: str,
    current_user: User = Depends(require_admin)
):
    """Force reset a GSV API key's rate limit status."""
    from app.services.gsv_key_manager import gsv_key_manager
    
    if gsv_key_manager.force_reset_key(key_prefix):
        return {"message": f"Key {key_prefix}... has been reset"}
    else:
        raise HTTPException(status_code=404, detail=f"Key starting with {key_prefix} not found")


@router.post("/gsv-keys-reload")
async def reload_gsv_keys(
    current_user: User = Depends(require_admin)
):
    """Reload GSV API keys from configuration."""
    from app.services.gsv_key_manager import gsv_key_manager
    
    gsv_key_manager.reload_keys()
    return gsv_key_manager.get_status()


@router.get("/gsv-diagnostic")
async def gsv_diagnostic(
    current_user: User = Depends(require_admin)
):
    """
    Diagnose Google Street View API configuration and test connectivity.
    
    This helps troubleshoot 403 errors and API issues.
    """
    import httpx
    from app.core.config import settings
    
    results = {
        "api_key_configured": False,
        "api_key_prefix": None,
        "api_key_length": 0,
        "metadata_test": None,
        "image_test": None,
        "recommendations": []
    }
    
    # Check API key
    api_key = settings.GSV_API_KEY
    if api_key:
        results["api_key_configured"] = True
        results["api_key_prefix"] = api_key[:8] + "..." if len(api_key) > 8 else api_key
        results["api_key_length"] = len(api_key)
    else:
        results["recommendations"].append("GSV_API_KEY environment variable is not set!")
        return results
    
    # Test location (London, UK - should have Street View coverage)
    test_lat = 51.5074
    test_lng = -0.1278
    
    # Test metadata endpoint
    metadata_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
    metadata_params = {
        "location": f"{test_lat},{test_lng}",
        "key": api_key
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(metadata_url, params=metadata_params)
            results["metadata_test"] = {
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text[:500]
            }
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK":
                    results["metadata_test"]["success"] = True
                else:
                    results["metadata_test"]["success"] = False
                    results["recommendations"].append(f"Metadata API returned status: {data.get('status')}. Check if Street View Static API is enabled.")
            elif response.status_code == 403:
                results["recommendations"].append("403 Forbidden - Check API key restrictions in Google Cloud Console. Remove any IP/referrer restrictions or add Render's IPs.")
            elif response.status_code == 400:
                results["recommendations"].append("400 Bad Request - The API key format may be invalid.")
    except Exception as e:
        results["metadata_test"] = {"error": str(e)}
        results["recommendations"].append(f"Failed to connect to Google API: {str(e)}")
    
    # Test image endpoint
    image_url = "https://maps.googleapis.com/maps/api/streetview"
    image_params = {
        "size": "100x100",
        "location": f"{test_lat},{test_lng}",
        "heading": 0,
        "key": api_key
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(image_url, params=image_params)
            results["image_test"] = {
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "content_length": len(response.content)
            }
            
            if response.status_code == 200 and "image" in response.headers.get("content-type", ""):
                results["image_test"]["success"] = True
            else:
                results["image_test"]["success"] = False
                if response.status_code == 403:
                    results["recommendations"].append("Image API returned 403. API key is being rejected. Check:")
                    results["recommendations"].append("1. Go to Google Cloud Console > APIs & Services > Credentials")
                    results["recommendations"].append("2. Find your API key and click on it")
                    results["recommendations"].append("3. Under 'Application restrictions', set to 'None' or add Render's IP ranges")
                    results["recommendations"].append("4. Under 'API restrictions', ensure 'Street View Static API' is allowed")
    except Exception as e:
        results["image_test"] = {"error": str(e)}
    
    # Add general recommendations
    if not results.get("recommendations"):
        if results.get("metadata_test", {}).get("success") and results.get("image_test", {}).get("success"):
            results["recommendations"].append("✅ GSV API is working correctly!")
        else:
            results["recommendations"].append("Check Google Cloud Console for more details on the errors.")
    
    return results


# ============================================
# GSV API Key Management
# ============================================

class GSVAccountCreate(BaseModel):
    """Create a GSV Google account entry."""
    email: str
    billing_id: str = ""
    target_projects: int = 30


class GSVAccountResponse(BaseModel):
    """GSV account response."""
    id: str
    email: str
    billing_id: str
    target_projects: int
    projects_created: int
    keys_generated: int
    created_at: datetime


# In-memory storage for GSV accounts (in production, you'd use the database)
# This is stored server-side for simplicity
import json
from pathlib import Path

GSV_DATA_FILE = Path("gsv_accounts_data.json")


def load_gsv_data():
    """Load GSV accounts data."""
    if GSV_DATA_FILE.exists():
        try:
            with open(GSV_DATA_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"accounts": [], "all_keys": []}


def save_gsv_data(data):
    """Save GSV accounts data."""
    with open(GSV_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


@router.get("/gsv-accounts")
async def get_gsv_accounts(
    current_user: User = Depends(require_admin)
):
    """Get all GSV accounts and their keys."""
    data = load_gsv_data()
    
    # Calculate stats
    total_projects = sum(len(a.get("projects", [])) for a in data["accounts"])
    total_keys = sum(1 for a in data["accounts"] for p in a.get("projects", []) if p.get("api_key"))
    
    return {
        "accounts": data["accounts"],
        "stats": {
            "total_accounts": len(data["accounts"]),
            "total_projects": total_projects,
            "total_keys": total_keys,
            "daily_capacity": total_keys * 25000,
            "estimated_hours_for_1_7m": round(1700000 / (total_keys * 25000), 1) if total_keys > 0 else 0
        }
    }


@router.post("/gsv-accounts")
async def add_gsv_account(
    account: GSVAccountCreate,
    current_user: User = Depends(require_admin)
):
    """Add a new GSV Google account."""
    data = load_gsv_data()
    
    # Check if account already exists
    if any(a["email"] == account.email for a in data["accounts"]):
        raise HTTPException(status_code=400, detail="Account already exists")
    
    new_account = {
        "id": str(uuid.uuid4()),
        "email": account.email,
        "billing_id": account.billing_id,
        "target_projects": account.target_projects,
        "projects": [],
        "created_at": datetime.utcnow().isoformat()
    }
    
    data["accounts"].append(new_account)
    save_gsv_data(data)
    
    return {"success": True, "account": new_account}


@router.delete("/gsv-accounts/{account_id}")
async def delete_gsv_account(
    account_id: str,
    current_user: User = Depends(require_admin)
):
    """Delete a GSV account entry."""
    data = load_gsv_data()
    
    data["accounts"] = [a for a in data["accounts"] if a.get("id") != account_id]
    save_gsv_data(data)
    
    return {"success": True}


@router.post("/gsv-accounts/{account_id}/add-key")
async def add_gsv_key_manually(
    account_id: str,
    key_data: dict,
    current_user: User = Depends(require_admin)
):
    """Manually add an API key to an account."""
    data = load_gsv_data()
    
    for account in data["accounts"]:
        if account.get("id") == account_id:
            if "projects" not in account:
                account["projects"] = []
            
            account["projects"].append({
                "project_id": key_data.get("project_id", f"manual-{len(account['projects']) + 1}"),
                "api_key": key_data.get("api_key"),
                "added_at": datetime.utcnow().isoformat()
            })
            
            save_gsv_data(data)
            return {"success": True}
    
    raise HTTPException(status_code=404, detail="Account not found")


@router.post("/gsv-accounts/{account_id}/bulk-add-keys")
async def bulk_add_gsv_keys(
    account_id: str,
    keys: dict,
    current_user: User = Depends(require_admin)
):
    """Bulk add API keys to an account (comma-separated or newline-separated)."""
    data = load_gsv_data()
    
    keys_text = keys.get("keys", "")
    # Split by comma or newline
    key_list = [k.strip() for k in keys_text.replace("\n", ",").split(",") if k.strip()]
    
    for account in data["accounts"]:
        if account.get("id") == account_id:
            if "projects" not in account:
                account["projects"] = []
            
            added = 0
            for i, key in enumerate(key_list):
                # Check if key already exists
                existing_keys = [p.get("api_key") for p in account["projects"]]
                if key not in existing_keys:
                    account["projects"].append({
                        "project_id": f"imported-{len(account['projects']) + 1}",
                        "api_key": key,
                        "added_at": datetime.utcnow().isoformat()
                    })
                    added += 1
            
            save_gsv_data(data)
            return {"success": True, "added": added, "total": len(account["projects"])}
    
    raise HTTPException(status_code=404, detail="Account not found")


@router.get("/gsv-all-keys")
async def get_all_gsv_keys(
    current_user: User = Depends(require_admin)
):
    """Get all GSV API keys as a comma-separated string for Render."""
    data = load_gsv_data()
    
    all_keys = []
    for account in data["accounts"]:
        for project in account.get("projects", []):
            if project.get("api_key"):
                all_keys.append(project["api_key"])
    
    return {
        "keys_string": ",".join(all_keys),
        "total_keys": len(all_keys),
        "daily_capacity": len(all_keys) * 25000
    }


@router.post("/gsv-apply-keys")
async def apply_gsv_keys_to_config(
    current_user: User = Depends(require_admin)
):
    """
    Apply all stored GSV keys to the running application config.
    This updates the GSV_API_KEYS setting in memory.
    """
    from app.core.config import settings
    
    data = load_gsv_data()
    
    all_keys = []
    for account in data["accounts"]:
        for project in account.get("projects", []):
            if project.get("api_key"):
                all_keys.append(project["api_key"])
    
    if all_keys:
        # Update settings (this affects the running instance)
        settings.GSV_API_KEYS = ",".join(all_keys)
        
        # Reload the key manager
        from app.services.gsv_key_manager import gsv_key_manager
        gsv_key_manager._initialized = False
        gsv_key_manager.__init__()
        
        return {
            "success": True,
            "keys_applied": len(all_keys),
            "message": f"Applied {len(all_keys)} keys to the running application"
        }
    
    return {"success": False, "message": "No keys to apply"}


# ============================================
# Google Cloud OAuth for Project Management
# ============================================

import urllib.parse

# Scopes needed for creating projects and API keys
GOOGLE_CLOUD_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/cloudplatformprojects", 
    "https://www.googleapis.com/auth/serviceusage",
    "https://www.googleapis.com/auth/cloud-billing",
    "openid",
    "email",
    "profile"
]


@router.get("/gsv-oauth-config")
async def get_gsv_oauth_config(
    current_user: User = Depends(require_admin)
):
    """Get current OAuth configuration for debugging."""
    from app.core.config import settings
    
    redirect_uri = settings.google_cloud_redirect_uri
    
    return {
        "backend_url": settings.BACKEND_URL or "(NOT SET - using localhost fallback)",
        "redirect_uri": redirect_uri,
        "google_client_id_set": bool(settings.GOOGLE_CLIENT_ID),
        "google_client_secret_set": bool(settings.GOOGLE_CLIENT_SECRET),
        "instructions": [
            "1. Set BACKEND_URL in Render to your backend URL (e.g., https://your-backend.onrender.com)",
            "2. Go to Google Cloud Console > APIs & Services > Credentials",
            "3. Edit your OAuth 2.0 Client ID",
            "4. Add this redirect URI to 'Authorized redirect URIs':",
            f"   {redirect_uri}",
            "5. Save and wait a few minutes for Google to propagate the changes"
        ]
    }


@router.get("/gsv-oauth-url")
async def get_gsv_oauth_url(
    current_user: User = Depends(require_admin)
):
    """Get Google OAuth URL for connecting a Google Cloud account."""
    from app.core.config import settings
    
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID in environment.")
    
    if not settings.BACKEND_URL:
        raise HTTPException(status_code=400, detail="BACKEND_URL not configured. Set it in Render environment (e.g., https://your-backend.onrender.com)")
    
    redirect_uri = settings.google_cloud_redirect_uri
    print(f"[GSV OAuth] Using redirect URI: {redirect_uri}")
    
    # Build OAuth URL
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_CLOUD_SCOPES),
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Always show consent to get refresh token
        "state": str(current_user.id)  # Pass user ID for security
    }
    
    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    return {"oauth_url": oauth_url, "redirect_uri": redirect_uri}


@router.get("/gsv-oauth-callback")
async def gsv_oauth_callback(
    code: str,
    state: str = None,
    error: str = None
):
    """Handle Google OAuth callback - exchange code for tokens."""
    from app.core.config import settings
    
    if error:
        # Redirect to frontend with error
        frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
        return RedirectResponse(f"{frontend_url}/admin?gsv_error={error}")
    
    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    redirect_uri = settings.google_cloud_redirect_uri
    print(f"[GSV OAuth Callback] Using redirect URI for token exchange: {redirect_uri}")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        })
        
        if response.status_code != 200:
            frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
            return RedirectResponse(f"{frontend_url}/admin?gsv_error=token_exchange_failed")
        
        tokens = response.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        
        # Get user info
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if userinfo_response.status_code == 200:
            userinfo = userinfo_response.json()
            email = userinfo.get("email")
            
            # Store the account with tokens
            data = load_gsv_data()
            
            # Check if account exists, update or create
            existing = next((a for a in data["accounts"] if a.get("email") == email), None)
            
            if existing:
                existing["access_token"] = access_token
                existing["refresh_token"] = refresh_token or existing.get("refresh_token")
                existing["connected"] = True
                existing["connected_at"] = datetime.utcnow().isoformat()
            else:
                data["accounts"].append({
                    "id": str(uuid.uuid4()),
                    "email": email,
                    "billing_id": "",
                    "target_projects": 30,
                    "projects": [],
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "connected": True,
                    "connected_at": datetime.utcnow().isoformat(),
                    "created_at": datetime.utcnow().isoformat()
                })
            
            save_gsv_data(data)
            
            # Redirect to frontend with success
            frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
            return RedirectResponse(f"{frontend_url}/admin?gsv_connected={email}")
        
        frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
        return RedirectResponse(f"{frontend_url}/admin?gsv_error=userinfo_failed")


async def refresh_google_token(account: dict) -> str:
    """Refresh an expired Google access token."""
    from app.core.config import settings
    
    refresh_token = account.get("refresh_token")
    if not refresh_token:
        raise Exception("No refresh token available")
    
    async with httpx.AsyncClient() as client:
        response = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        })
        
        if response.status_code == 200:
            tokens = response.json()
            return tokens.get("access_token")
        
        raise Exception(f"Token refresh failed: {response.text}")


@router.post("/gsv-accounts/{account_id}/create-projects")
async def create_gsv_projects(
    account_id: str,
    count: int = Query(default=5, ge=1, le=30),
    current_user: User = Depends(require_admin)
):
    """
    Automatically create Google Cloud projects and API keys for a connected account.
    
    This requires the account to be connected via OAuth with the right permissions.
    """
    data = load_gsv_data()
    
    account = next((a for a in data["accounts"] if a.get("id") == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    if not account.get("connected") or not account.get("access_token"):
        raise HTTPException(status_code=400, detail="Account not connected. Please sign in with Google first.")
    
    access_token = account.get("access_token")
    
    # Try to refresh token if needed
    try:
        # Test if token is valid
        async with httpx.AsyncClient() as client:
            test_response = await client.get(
                "https://cloudresourcemanager.googleapis.com/v1/projects",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"pageSize": 1}
            )
            
            if test_response.status_code == 401:
                # Token expired, refresh it
                access_token = await refresh_google_token(account)
                account["access_token"] = access_token
                save_gsv_data(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to authenticate: {str(e)}")
    
    created_projects = []
    failed_projects = []
    
    email_prefix = account["email"].split("@")[0][:8]
    existing_count = len(account.get("projects", []))
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(count):
            project_num = existing_count + i + 1
            project_id = f"gsv-{email_prefix}-{project_num}-{uuid.uuid4().hex[:4]}"
            
            try:
                # Step 1: Create project
                create_response = await client.post(
                    "https://cloudresourcemanager.googleapis.com/v1/projects",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"projectId": project_id, "name": f"GSV Download {project_num}"}
                )
                
                if create_response.status_code not in [200, 409]:  # 409 = already exists
                    failed_projects.append({"project_id": project_id, "error": f"Create failed: {create_response.text[:200]}"})
                    continue
                
                # Wait for project to be created
                await asyncio.sleep(2)
                
                # Step 2: Enable Street View API
                enable_response = await client.post(
                    f"https://serviceusage.googleapis.com/v1/projects/{project_id}/services/streetviewpublish.googleapis.com:enable",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                # Step 3: Create API key
                await asyncio.sleep(1)
                
                key_response = await client.post(
                    f"https://apikeys.googleapis.com/v2/projects/{project_id}/locations/global/keys",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"displayName": f"GSV-Key-{project_num}"}
                )
                
                api_key = None
                if key_response.status_code == 200:
                    key_data = key_response.json()
                    # The key string is in the response
                    api_key = key_data.get("keyString")
                    
                    if not api_key:
                        # Need to get the key string separately
                        key_name = key_data.get("name")
                        if key_name:
                            key_string_response = await client.get(
                                f"https://apikeys.googleapis.com/v2/{key_name}/keyString",
                                headers={"Authorization": f"Bearer {access_token}"}
                            )
                            if key_string_response.status_code == 200:
                                api_key = key_string_response.json().get("keyString")
                
                # Add to account projects
                if "projects" not in account:
                    account["projects"] = []
                
                account["projects"].append({
                    "project_id": project_id,
                    "api_key": api_key,
                    "created_at": datetime.utcnow().isoformat(),
                    "auto_created": True
                })
                
                created_projects.append({
                    "project_id": project_id,
                    "api_key": api_key[:20] + "..." if api_key else None
                })
                
            except Exception as e:
                failed_projects.append({"project_id": project_id, "error": str(e)})
    
    save_gsv_data(data)
    
    return {
        "success": True,
        "created": len(created_projects),
        "failed": len(failed_projects),
        "created_projects": created_projects,
        "failed_projects": failed_projects,
        "total_keys": len([p for p in account.get("projects", []) if p.get("api_key")])
    }


# Need to import for RedirectResponse
from fastapi.responses import RedirectResponse
import asyncio