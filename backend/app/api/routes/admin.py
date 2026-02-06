"""Admin routes for system management and reporting."""
import uuid
import asyncio
import httpx
import urllib.parse
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete
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


# ============================================
# GSV API Key Management (Simplified)
# ============================================

from app.models.gsv_api_key import GSVApiKey


class BulkKeysRequest(BaseModel):
    """Request to bulk add API keys."""
    keys: str  # Comma or newline separated keys


class KeyUpdateRequest(BaseModel):
    """Request to update a key."""
    is_active: Optional[bool] = None
    label: Optional[str] = None


@router.get("/gsv-keys")
async def get_gsv_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get all GSV API keys with usage stats.
    
    Returns keys with masked values (only prefix shown for security).
    """
    from app.services.gsv_key_manager import gsv_key_manager
    
    # Get keys from database
    result = await db.execute(
        select(GSVApiKey).order_by(GSVApiKey.created_at.desc())
    )
    db_keys = result.scalars().all()
    
    # Get in-memory stats from key manager
    memory_status = gsv_key_manager.get_status()
    memory_stats = {k["key_prefix"]: k for k in memory_status.get("keys", [])}
    
    keys_data = []
    total_requests_today = 0
    active_count = 0
    exhausted_count = 0
    
    for db_key in db_keys:
        # Merge DB data with in-memory stats
        prefix = db_key.api_key[:12]
        mem_stats = memory_stats.get(prefix + "...", {})
        
        # Use in-memory requests_today if available (more current)
        requests_today = mem_stats.get("requests_today", db_key.requests_today)
        
        key_data = db_key.to_dict(include_full_key=False)
        key_data["requests_today"] = requests_today
        
        keys_data.append(key_data)
        total_requests_today += requests_today
        
        if db_key.is_active and not db_key.quota_exhausted:
            active_count += 1
        if db_key.quota_exhausted:
            exhausted_count += 1
    
    return {
        "keys": keys_data,
        "summary": {
            "total_keys": len(db_keys),
            "active_keys": active_count,
            "exhausted_keys": exhausted_count,
            "disabled_keys": len(db_keys) - active_count - exhausted_count,
            "total_requests_today": total_requests_today,
            "daily_capacity": active_count * 25000,
            "estimated_hours_for_1_7m": round(1700000 / (active_count * 25000), 1) if active_count > 0 else 0
        }
    }


@router.post("/gsv-keys/bulk")
async def bulk_add_gsv_keys(
    request: BulkKeysRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Bulk add GSV API keys.
    
    Accepts comma-separated or newline-separated keys.
    Duplicates are automatically skipped.
    """
    from app.services.gsv_key_manager import gsv_key_manager
    
    # Parse keys (handle both comma and newline separators)
    raw_keys = request.keys.replace("\n", ",").replace("\r", "")
    keys_list = [k.strip() for k in raw_keys.split(",") if k.strip()]
    
    # Filter valid API keys (Google API keys start with "AIza")
    valid_keys = [k for k in keys_list if k.startswith("AIza") and len(k) >= 30]
    
    if not valid_keys:
        raise HTTPException(
            status_code=400, 
            detail="No valid API keys found. Google API keys start with 'AIza' and are ~39 characters."
        )
    
    # Check for existing keys
    existing_result = await db.execute(
        select(GSVApiKey.api_key).where(GSVApiKey.api_key.in_(valid_keys))
    )
    existing_keys = set(existing_result.scalars().all())
    
    # Add new keys
    added = 0
    skipped = 0
    
    for key in valid_keys:
        if key in existing_keys:
            skipped += 1
            continue
        
        new_key = GSVApiKey(
            api_key=key,
            label=None,
            is_active=True,
        )
        db.add(new_key)
        added += 1
        
        # Add to in-memory manager
        gsv_key_manager.add_key_to_memory(key, str(new_key.id))
    
    await db.commit()
    
    # Reload keys in manager
    await gsv_key_manager.load_keys_from_db(db)
    
    return {
        "success": True,
        "added": added,
        "skipped": skipped,
        "total_submitted": len(valid_keys),
        "message": f"Added {added} new keys. {skipped} duplicates skipped."
    }


@router.delete("/gsv-keys/{key_id}")
async def delete_gsv_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a GSV API key."""
    from app.services.gsv_key_manager import gsv_key_manager
    
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID")
    
    # Get the key first to get the api_key value
    result = await db.execute(
        select(GSVApiKey).where(GSVApiKey.id == key_uuid)
    )
    db_key = result.scalar_one_or_none()
    
    if not db_key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    api_key = db_key.api_key
    
    # Delete from database
    await db.execute(
        delete(GSVApiKey).where(GSVApiKey.id == key_uuid)
    )
    await db.commit()
    
    # Remove from in-memory manager
    gsv_key_manager.remove_key_from_memory(api_key)
    
    return {"success": True, "message": "Key deleted"}


@router.patch("/gsv-keys/{key_id}")
async def update_gsv_key(
    key_id: str,
    request: KeyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a GSV API key (enable/disable, set label)."""
    from app.services.gsv_key_manager import gsv_key_manager
    
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID")
    
    # Get the key
    result = await db.execute(
        select(GSVApiKey).where(GSVApiKey.id == key_uuid)
    )
    db_key = result.scalar_one_or_none()
    
    if not db_key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    # Update fields
    if request.is_active is not None:
        db_key.is_active = request.is_active
    if request.label is not None:
        db_key.label = request.label
    
    await db.commit()
    
    # Reload keys in manager
    await gsv_key_manager.load_keys_from_db(db)
    
    return {
        "success": True,
        "key": db_key.to_dict(include_full_key=False)
    }


@router.post("/gsv-keys/reset/{key_prefix}")
async def reset_gsv_key(
    key_prefix: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Reset a GSV API key's error/quota status.
    
    Use this to manually re-enable a key that was marked as quota exhausted.
    """
    from app.services.gsv_key_manager import gsv_key_manager
    
    # Find key in database
    result = await db.execute(
        select(GSVApiKey).where(GSVApiKey.api_key.startswith(key_prefix))
    )
    db_key = result.scalar_one_or_none()
    
    if not db_key:
        raise HTTPException(status_code=404, detail=f"Key starting with {key_prefix} not found")
    
    # Reset in database
    db_key.quota_exhausted = False
    db_key.consecutive_errors = 0
    db_key.last_error_at = None
    db_key.last_error_message = None
    await db.commit()
    
    # Reset in memory
    gsv_key_manager.force_reset_key(key_prefix)
    
    return {
        "success": True,
        "message": f"Key {key_prefix}... has been reset",
        "key": db_key.to_dict(include_full_key=False)
    }


@router.get("/gsv-keys/status")
async def get_gsv_keys_status(
    current_user: User = Depends(require_admin)
):
    """Get real-time status of GSV API keys from the key manager."""
    from app.services.gsv_key_manager import gsv_key_manager
    
    return gsv_key_manager.get_status()


@router.post("/gsv-keys/sync")
async def sync_gsv_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Sync GSV API keys between database and memory.
    
    - Loads keys from database into the key manager
    - Persists in-memory stats back to database
    """
    from app.services.gsv_key_manager import gsv_key_manager
    
    # Sync stats to DB first
    await gsv_key_manager.sync_stats_to_db(db)
    
    # Then load keys from DB
    count = await gsv_key_manager.load_keys_from_db(db)
    
    return {
        "success": True,
        "keys_loaded": count,
        "status": gsv_key_manager.get_status()
    }


@router.get("/gsv-diagnostic")
async def gsv_diagnostic(
    current_user: User = Depends(require_admin)
):
    """
    Diagnose Google Street View API configuration and test connectivity.
    """
    from app.services.gsv_key_manager import gsv_key_manager
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "key_manager_status": gsv_key_manager.get_status(),
        "tests": []
    }
    
    # Test with first available key
    test_key = await gsv_key_manager.get_key()
    
    if not test_key:
        results["tests"].append({
            "name": "API Key Availability",
            "status": "FAIL",
            "message": "No API keys available"
        })
        return results
    
    results["tests"].append({
        "name": "API Key Availability",
        "status": "PASS",
        "message": f"Using key {test_key[:12]}..."
    })
    
    # Test metadata endpoint
    test_lat, test_lng = 51.5074, -0.1278  # London
    metadata_url = f"https://maps.googleapis.com/maps/api/streetview/metadata?location={test_lat},{test_lng}&key={test_key}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(metadata_url)
            
            if response.status_code == 200:
                data = response.json()
                results["tests"].append({
                    "name": "Metadata API",
                    "status": "PASS" if data.get("status") == "OK" else "WARN",
                    "message": f"Status: {data.get('status')}",
                    "response": data
                })
            elif response.status_code == 403:
                results["tests"].append({
                    "name": "Metadata API",
                    "status": "FAIL",
                    "message": "403 Forbidden - Key may be invalid or quota exceeded",
                    "response": response.text[:200]
                })
            else:
                results["tests"].append({
                    "name": "Metadata API",
                    "status": "FAIL",
                    "message": f"HTTP {response.status_code}",
                    "response": response.text[:200]
                })
        except Exception as e:
            results["tests"].append({
                "name": "Metadata API",
                "status": "FAIL",
                "message": f"Error: {str(e)}"
            })
    
    return results
