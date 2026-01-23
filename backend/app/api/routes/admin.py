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