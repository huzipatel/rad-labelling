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

