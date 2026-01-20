"""Task management routes."""
import uuid
import json
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text, delete
from sqlalchemy.orm import selectinload, joinedload
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.location import Location, LocationType
from app.models.task import Task
from app.models.label import Label
from app.api.deps import get_current_user, require_manager, require_labeller
from app.services.gsv_downloader import GSVDownloader


router = APIRouter(prefix="/tasks", tags=["Tasks"])


class TaskCreate(BaseModel):
    """Create task request."""
    location_type_id: str
    council: str


class TaskAssign(BaseModel):
    """Assign task request."""
    labeller_id: str


class BulkAssign(BaseModel):
    """Bulk assign tasks request."""
    task_ids: List[str]
    labeller_id: str


class TaskResponse(BaseModel):
    """Task response model."""
    id: str
    location_type_id: str
    location_type_name: str
    council: str
    group_field: Optional[str] = None
    group_value: Optional[str] = None
    name: Optional[str] = None
    assigned_to: Optional[str]
    assignee_name: Optional[str]
    status: str
    total_locations: int
    completed_locations: int
    failed_locations: int
    images_downloaded: int
    total_images: int
    completion_percentage: float
    download_progress: float
    created_at: datetime
    assigned_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class TaskListResponse(BaseModel):
    """Paginated task list."""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskStats(BaseModel):
    """Task statistics."""
    total_tasks: int
    pending: int
    downloading: int
    ready: int
    in_progress: int
    completed: int


class GroupableField(BaseModel):
    """A field that can be used to group tasks."""
    key: str
    label: str
    source: str  # 'enhanced' or 'original'
    distinct_values: int
    sample_values: List[str]


class TaskPreviewItem(BaseModel):
    """Preview of a single task that would be created."""
    group_value: str
    location_count: int
    already_exists: bool


class TaskCreationPreview(BaseModel):
    """Preview of task creation."""
    location_type_id: str
    location_type_name: str
    group_field: str
    group_field_label: str
    tasks_to_create: List[TaskPreviewItem]
    total_tasks: int
    total_locations: int
    existing_tasks: int
    new_tasks: int


class CreateTasksRequest(BaseModel):
    """Request to create tasks."""
    location_type_id: str
    group_field: str  # Field to group by (e.g., 'council', 'original_LocalityName')
    selected_values: Optional[List[str]] = None  # If None, create for all values


class LocationFilterRequest(BaseModel):
    """Request to filter locations in tasks."""
    location_type_id: str
    filter_field: str  # Field to filter on (e.g., 'original_Status')
    filter_value: str  # Value to match (e.g., 'Deleted')
    action: str  # 'preview' or 'remove'


class LocationFilterPreview(BaseModel):
    """Preview of locations that would be affected by a filter."""
    location_type_id: str
    filter_field: str
    filter_value: str
    total_matching: int
    tasks_affected: List[dict]  # List of {task_id, task_name, locations_affected}


@router.get("/groupable-fields/{location_type_id}", response_model=List[GroupableField])
async def get_groupable_fields(
    location_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get all fields that can be used to group locations into tasks."""
    # Verify location type exists
    lt_result = await db.execute(
        select(LocationType).where(LocationType.id == location_type_id)
    )
    location_type = lt_result.scalar_one_or_none()
    if not location_type:
        raise HTTPException(status_code=404, detail="Location type not found")
    
    groupable_fields = []
    
    # Enhanced fields (council, combined_authority, road_classification)
    enhanced_fields = [
        ("council", "Council", Location.council),
        ("combined_authority", "Combined Authority", Location.combined_authority),
        ("road_classification", "Road Classification", Location.road_classification),
    ]
    
    for field_key, field_label, column in enhanced_fields:
        # Get distinct count and samples
        result = await db.execute(
            select(column, func.count(Location.id).label("cnt"))
            .where(Location.location_type_id == location_type_id, column.isnot(None))
            .group_by(column)
            .order_by(func.count(Location.id).desc())
            .limit(20)
        )
        rows = result.all()
        
        if rows:
            groupable_fields.append(GroupableField(
                key=field_key,
                label=field_label,
                source="enhanced",
                distinct_values=len(rows),
                sample_values=[str(r[0]) for r in rows[:10]]
            ))
    
    # Original data fields from JSONB
    try:
        keys_result = await db.execute(
            text("""
                SELECT DISTINCT key
                FROM locations, jsonb_object_keys(original_data) AS key
                WHERE location_type_id = :lt_id
                AND original_data IS NOT NULL
                ORDER BY key
            """),
            {"lt_id": str(location_type_id)}
        )
        original_keys = [row[0] for row in keys_result.fetchall()]
        
        # Skip coordinate-like columns
        coord_keys = {'latitude', 'longitude', 'lat', 'lng', 'long', 'lon', 'x', 'y', 'easting', 'northing'}
        
        for key in original_keys:
            if key.lower() in coord_keys:
                continue
            
            # Get distinct values for this key
            values_result = await db.execute(
                text("""
                    SELECT original_data->>:key as val, COUNT(*) as cnt
                    FROM locations
                    WHERE location_type_id = :lt_id
                    AND original_data->>:key IS NOT NULL
                    AND original_data->>:key != ''
                    GROUP BY original_data->>:key
                    ORDER BY cnt DESC
                    LIMIT 100
                """),
                {"lt_id": str(location_type_id), "key": key}
            )
            rows = values_result.fetchall()
            
            # Only include fields with reasonable number of distinct values (2-500)
            if 2 <= len(rows) <= 500:
                groupable_fields.append(GroupableField(
                    key=f"original_{key}",
                    label=key,
                    source="original",
                    distinct_values=len(rows),
                    sample_values=[str(r[0]) for r in rows[:10]]
                ))
    except Exception as e:
        print(f"Error getting original data keys: {e}")
    
    return groupable_fields


@router.post("/preview", response_model=TaskCreationPreview)
async def preview_task_creation(
    request: CreateTasksRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Preview what tasks would be created for a given grouping field."""
    location_type_id = uuid.UUID(request.location_type_id)
    group_field = request.group_field
    
    # Verify location type exists
    lt_result = await db.execute(
        select(LocationType).where(LocationType.id == location_type_id)
    )
    location_type = lt_result.scalar_one_or_none()
    if not location_type:
        raise HTTPException(status_code=404, detail="Location type not found")
    
    # Determine if this is an enhanced field or original data field
    is_original = group_field.startswith("original_")
    original_key = group_field.replace("original_", "") if is_original else None
    
    # Get distinct values and counts
    if is_original:
        values_result = await db.execute(
            text("""
                SELECT original_data->>:key as val, COUNT(*) as cnt
                FROM locations
                WHERE location_type_id = :lt_id
                AND original_data->>:key IS NOT NULL
                AND original_data->>:key != ''
                GROUP BY original_data->>:key
                ORDER BY cnt DESC
            """),
            {"lt_id": str(location_type_id), "key": original_key}
        )
        rows = values_result.fetchall()
        group_data = [(r[0], r[1]) for r in rows]
        field_label = original_key
    else:
        # Enhanced field
        column_map = {
            "council": Location.council,
            "combined_authority": Location.combined_authority,
            "road_classification": Location.road_classification,
        }
        column = column_map.get(group_field)
        if not column:
            raise HTTPException(status_code=400, detail=f"Unknown group field: {group_field}")
        
        result = await db.execute(
            select(column, func.count(Location.id).label("cnt"))
            .where(Location.location_type_id == location_type_id, column.isnot(None))
            .group_by(column)
            .order_by(func.count(Location.id).desc())
        )
        rows = result.all()
        group_data = [(r[0], r[1]) for r in rows]
        field_label = group_field.replace("_", " ").title()
    
    # Check for existing tasks
    existing_result = await db.execute(
        select(Task.group_value).where(
            Task.location_type_id == location_type_id,
            Task.group_field == group_field
        )
    )
    existing_values = {r[0] for r in existing_result.all()}
    
    # Build preview
    tasks_preview = []
    total_locations = 0
    existing_count = 0
    
    for value, count in group_data:
        if request.selected_values and value not in request.selected_values:
            continue
        
        already_exists = value in existing_values
        if already_exists:
            existing_count += 1
        
        tasks_preview.append(TaskPreviewItem(
            group_value=value,
            location_count=count,
            already_exists=already_exists
        ))
        total_locations += count
    
    return TaskCreationPreview(
        location_type_id=str(location_type_id),
        location_type_name=location_type.display_name,
        group_field=group_field,
        group_field_label=field_label,
        tasks_to_create=tasks_preview,
        total_tasks=len(tasks_preview),
        total_locations=total_locations,
        existing_tasks=existing_count,
        new_tasks=len(tasks_preview) - existing_count
    )


@router.post("/create-from-field")
async def create_tasks_from_field(
    request: CreateTasksRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create tasks by grouping locations on a specified field."""
    location_type_id = uuid.UUID(request.location_type_id)
    group_field = request.group_field
    
    # Verify location type exists
    lt_result = await db.execute(
        select(LocationType).where(LocationType.id == location_type_id)
    )
    location_type = lt_result.scalar_one_or_none()
    if not location_type:
        raise HTTPException(status_code=404, detail="Location type not found")
    
    # Determine if this is an enhanced field or original data field
    is_original = group_field.startswith("original_")
    original_key = group_field.replace("original_", "") if is_original else None
    
    # Get distinct values and counts
    if is_original:
        values_result = await db.execute(
            text("""
                SELECT original_data->>:key as val, COUNT(*) as cnt
                FROM locations
                WHERE location_type_id = :lt_id
                AND original_data->>:key IS NOT NULL
                AND original_data->>:key != ''
                GROUP BY original_data->>:key
                ORDER BY cnt DESC
            """),
            {"lt_id": str(location_type_id), "key": original_key}
        )
        rows = values_result.fetchall()
        group_data = [(r[0], r[1]) for r in rows]
    else:
        # Enhanced field
        column_map = {
            "council": Location.council,
            "combined_authority": Location.combined_authority,
            "road_classification": Location.road_classification,
        }
        column = column_map.get(group_field)
        if not column:
            raise HTTPException(status_code=400, detail=f"Unknown group field: {group_field}")
        
        result = await db.execute(
            select(column, func.count(Location.id).label("cnt"))
            .where(Location.location_type_id == location_type_id, column.isnot(None))
            .group_by(column)
            .order_by(func.count(Location.id).desc())
        )
        rows = result.all()
        group_data = [(r[0], r[1]) for r in rows]
    
    if not group_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No locations found with values for field: {group_field}"
        )
    
    tasks_created = 0
    tasks_skipped = 0
    
    for value, count in group_data:
        # Skip if not in selected values (if specified)
        if request.selected_values and value not in request.selected_values:
            continue
        
        # Check if task already exists for this group
        existing = await db.execute(
            select(Task).where(
                Task.location_type_id == location_type_id,
                Task.group_field == group_field,
                Task.group_value == value
            )
        )
        if existing.scalar_one_or_none():
            tasks_skipped += 1
            continue
        
        # Create task
        # For council field, also populate the legacy council column
        council_value = value if group_field == "council" else None
        
        task = Task(
            location_type_id=location_type_id,
            council=council_value or value[:255],  # Use value for legacy field too
            group_field=group_field,
            group_value=value,
            name=f"{location_type.display_name} - {value}",
            status="pending",
            total_locations=count,
            total_images=count * 4  # 4 images per location
        )
        db.add(task)
        tasks_created += 1
    
    await db.commit()
    
    return {
        "message": f"Created {tasks_created} tasks" + (f", skipped {tasks_skipped} existing" if tasks_skipped > 0 else ""),
        "tasks_created": tasks_created,
        "tasks_skipped": tasks_skipped
    }


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete a task."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Don't allow deleting tasks that have labels
    labels_result = await db.execute(
        select(func.count(Label.id)).where(Label.task_id == task_id)
    )
    labels_count = labels_result.scalar()
    
    if labels_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete task with {labels_count} labels. Remove labels first."
        )
    
    await db.delete(task)
    await db.commit()
    
    return {"message": "Task deleted"}


@router.delete("/bulk-delete")
async def bulk_delete_tasks(
    task_ids: List[str],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete multiple tasks."""
    deleted_count = 0
    skipped_count = 0
    
    for task_id_str in task_ids:
        task_id = uuid.UUID(task_id_str)
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        
        if not task:
            continue
        
        # Check for labels
        labels_result = await db.execute(
            select(func.count(Label.id)).where(Label.task_id == task_id)
        )
        if labels_result.scalar() > 0:
            skipped_count += 1
            continue
        
        await db.delete(task)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"Deleted {deleted_count} tasks" + (f", skipped {skipped_count} with labels" if skipped_count > 0 else ""),
        "deleted_count": deleted_count,
        "skipped_count": skipped_count
    }


# ============================================
# Location Filtering Endpoints
# ============================================

@router.get("/location-filter-fields/{location_type_id}")
async def get_location_filter_fields(
    location_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get all fields in the original location data that can be used for filtering."""
    # Get all unique keys from original_data
    try:
        keys_result = await db.execute(
            text("""
                SELECT DISTINCT key
                FROM locations, jsonb_object_keys(original_data) AS key
                WHERE location_type_id = :lt_id
                AND original_data IS NOT NULL
                ORDER BY key
            """),
            {"lt_id": str(location_type_id)}
        )
        all_keys = [row[0] for row in keys_result.fetchall()]
        
        # Get sample values for each key
        fields = []
        for key in all_keys:
            values_result = await db.execute(
                text("""
                    SELECT original_data->>:key as val, COUNT(*) as cnt
                    FROM locations
                    WHERE location_type_id = :lt_id
                    AND original_data->>:key IS NOT NULL
                    GROUP BY original_data->>:key
                    ORDER BY cnt DESC
                    LIMIT 50
                """),
                {"lt_id": str(location_type_id), "key": key}
            )
            values = [{"value": r[0], "count": r[1]} for r in values_result.fetchall()]
            
            if values:
                fields.append({
                    "key": key,
                    "values": values,
                    "distinct_count": len(values)
                })
        
        return {"fields": fields}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/filter-locations/preview")
async def preview_location_filter(
    request: LocationFilterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Preview which locations would be affected by a filter."""
    location_type_id = uuid.UUID(request.location_type_id)
    filter_field = request.filter_field
    filter_value = request.filter_value
    
    # Count matching locations
    count_result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM locations
            WHERE location_type_id = :lt_id
            AND original_data->>:field = :value
        """),
        {"lt_id": str(location_type_id), "field": filter_field, "value": filter_value}
    )
    total_matching = count_result.scalar()
    
    # Get tasks and how many locations in each would be affected
    # Tasks are based on group_field/group_value
    tasks_result = await db.execute(
        select(Task).options(selectinload(Task.location_type)).where(
            Task.location_type_id == location_type_id
        )
    )
    tasks = tasks_result.scalars().all()
    
    tasks_affected = []
    for task in tasks:
        # Count locations in this task's group that match the filter
        if task.group_field and task.group_field.startswith("original_"):
            original_key = task.group_field.replace("original_", "")
            affected_result = await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM locations
                    WHERE location_type_id = :lt_id
                    AND original_data->>:group_key = :group_value
                    AND original_data->>:filter_field = :filter_value
                """),
                {
                    "lt_id": str(location_type_id),
                    "group_key": original_key,
                    "group_value": task.group_value,
                    "filter_field": filter_field,
                    "filter_value": filter_value
                }
            )
        else:
            # Enhanced field grouping (council, etc.)
            column_name = task.group_field or "council"
            affected_result = await db.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM locations
                    WHERE location_type_id = :lt_id
                    AND {column_name} = :group_value
                    AND original_data->>:filter_field = :filter_value
                """),
                {
                    "lt_id": str(location_type_id),
                    "group_value": task.group_value,
                    "filter_field": filter_field,
                    "filter_value": filter_value
                }
            )
        
        affected_count = affected_result.scalar()
        if affected_count > 0:
            tasks_affected.append({
                "task_id": str(task.id),
                "task_name": task.name or task.group_value or task.council,
                "total_locations": task.total_locations,
                "locations_affected": affected_count,
                "new_total": task.total_locations - affected_count
            })
    
    return {
        "location_type_id": str(location_type_id),
        "filter_field": filter_field,
        "filter_value": filter_value,
        "total_matching": total_matching,
        "tasks_affected": tasks_affected,
        "total_tasks_affected": len(tasks_affected)
    }


@router.post("/filter-locations/apply")
async def apply_location_filter(
    request: LocationFilterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Remove locations matching a filter from the dataset and update task counts."""
    location_type_id = uuid.UUID(request.location_type_id)
    filter_field = request.filter_field
    filter_value = request.filter_value
    
    # First, check if any of these locations have labels
    labelled_check = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM labels l
            JOIN locations loc ON l.location_id = loc.id
            WHERE loc.location_type_id = :lt_id
            AND loc.original_data->>:field = :value
        """),
        {"lt_id": str(location_type_id), "field": filter_field, "value": filter_value}
    )
    labelled_count = labelled_check.scalar()
    
    if labelled_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove {labelled_count} locations that have already been labelled. Remove labels first."
        )
    
    # Delete matching locations
    delete_result = await db.execute(
        text("""
            DELETE FROM locations
            WHERE location_type_id = :lt_id
            AND original_data->>:field = :value
            RETURNING id
        """),
        {"lt_id": str(location_type_id), "field": filter_field, "value": filter_value}
    )
    deleted_ids = delete_result.fetchall()
    deleted_count = len(deleted_ids)
    
    # Update task counts
    tasks_result = await db.execute(
        select(Task).where(Task.location_type_id == location_type_id)
    )
    tasks = tasks_result.scalars().all()
    
    tasks_updated = 0
    for task in tasks:
        # Recalculate total locations for this task
        if task.group_field and task.group_field.startswith("original_"):
            original_key = task.group_field.replace("original_", "")
            new_count_result = await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM locations
                    WHERE location_type_id = :lt_id
                    AND original_data->>:group_key = :group_value
                """),
                {
                    "lt_id": str(location_type_id),
                    "group_key": original_key,
                    "group_value": task.group_value
                }
            )
        else:
            column_name = task.group_field or "council"
            new_count_result = await db.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM locations
                    WHERE location_type_id = :lt_id
                    AND {column_name} = :group_value
                """),
                {
                    "lt_id": str(location_type_id),
                    "group_value": task.group_value
                }
            )
        
        new_count = new_count_result.scalar()
        if new_count != task.total_locations:
            task.total_locations = new_count
            task.total_images = new_count * 4
            tasks_updated += 1
    
    await db.commit()
    
    return {
        "message": f"Removed {deleted_count} locations where {filter_field} = '{filter_value}'",
        "locations_removed": deleted_count,
        "tasks_updated": tasks_updated
    }


@router.post("/generate")
async def generate_tasks(
    location_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Generate tasks for all councils in a location type (legacy endpoint)."""
    # Get all councils for this location type
    result = await db.execute(
        select(Location.council, func.count(Location.id).label("count"))
        .where(
            Location.location_type_id == location_type_id,
            Location.council.isnot(None)
        )
        .group_by(Location.council)
    )
    councils = result.all()
    
    if not councils:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No enhanced locations found. Please upload and enhance data first."
        )
    
    tasks_created = 0
    for council_data in councils:
        # Check if task already exists
        existing = await db.execute(
            select(Task).where(
                Task.location_type_id == location_type_id,
                Task.council == council_data.council
            )
        )
        if existing.scalar_one_or_none():
            continue
        
        # Create task
        task = Task(
            location_type_id=location_type_id,
            council=council_data.council,
            group_field="council",
            group_value=council_data.council,
            name=council_data.council,
            status="pending",
            total_locations=council_data.count,
            total_images=council_data.count * 4  # 4 images per location
        )
        db.add(task)
        tasks_created += 1
    
    await db.commit()
    
    return {
        "message": f"Generated {tasks_created} tasks",
        "tasks_created": tasks_created
    }


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    location_type_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,  # Can be UUID or "unassigned"
    council: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List all tasks (manager only)."""
    # Use selectinload to eagerly load relationships
    query = select(Task).options(
        selectinload(Task.location_type),
        selectinload(Task.assignee)
    )
    count_query = select(func.count(Task.id))
    
    # Apply filters
    filters = []
    if location_type_id:
        filters.append(Task.location_type_id == location_type_id)
    if status:
        filters.append(Task.status == status)
    if assigned_to:
        if assigned_to == "unassigned":
            filters.append(Task.assigned_to.is_(None))
        else:
            try:
                assignee_id = uuid.UUID(assigned_to)
                filters.append(Task.assigned_to == assignee_id)
            except ValueError:
                pass  # Invalid UUID, ignore filter
    if council:
        # Search in both council and group_value
        filters.append(
            (Task.council.ilike(f"%{council}%")) | 
            (Task.group_value.ilike(f"%{council}%")) |
            (Task.name.ilike(f"%{council}%"))
        )
    
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
    
    # Get total
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get paginated results
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Task.created_at.desc())
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Build response
    task_responses = []
    for task in tasks:
        # Get assignee name
        assignee_name = None
        if task.assignee:
            assignee_name = task.assignee.name
        
        task_responses.append(TaskResponse(
            id=str(task.id),
            location_type_id=str(task.location_type_id),
            location_type_name=task.location_type.display_name,
            council=task.council,
            group_field=task.group_field,
            group_value=task.group_value,
            name=task.name or task.council,
            assigned_to=str(task.assigned_to) if task.assigned_to else None,
            assignee_name=assignee_name,
            status=task.status,
            total_locations=task.total_locations,
            completed_locations=task.completed_locations,
            failed_locations=task.failed_locations,
            images_downloaded=task.images_downloaded,
            total_images=task.total_images,
            completion_percentage=task.completion_percentage,
            download_progress=task.download_progress,
            created_at=task.created_at,
            assigned_at=task.assigned_at,
            started_at=task.started_at,
            completed_at=task.completed_at
        ))
    
    return TaskListResponse(
        tasks=task_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/my-tasks", response_model=List[TaskResponse])
async def get_my_tasks(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get tasks assigned to current user (works for both labellers and managers)."""
    query = select(Task).options(
        selectinload(Task.location_type),
        selectinload(Task.assignee)
    ).where(Task.assigned_to == current_user.id)
    
    if status:
        query = query.where(Task.status == status)
    
    query = query.order_by(Task.assigned_at.desc())
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return [
        TaskResponse(
            id=str(t.id),
            location_type_id=str(t.location_type_id),
            location_type_name=t.location_type.display_name,
            council=t.council,
            group_field=t.group_field,
            group_value=t.group_value,
            name=t.name or t.council,
            assigned_to=str(t.assigned_to) if t.assigned_to else None,
            assignee_name=current_user.name,
            status=t.status,
            total_locations=t.total_locations,
            completed_locations=t.completed_locations,
            failed_locations=t.failed_locations,
            images_downloaded=t.images_downloaded,
            total_images=t.total_images,
            completion_percentage=t.completion_percentage,
            download_progress=t.download_progress,
            created_at=t.created_at,
            assigned_at=t.assigned_at,
            started_at=t.started_at,
            completed_at=t.completed_at
        )
        for t in tasks
    ]


@router.get("/stats", response_model=TaskStats)
async def get_task_stats(
    location_type_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get task statistics."""
    base_query = select(Task)
    if location_type_id:
        base_query = base_query.where(Task.location_type_id == location_type_id)
    
    # Count by status
    statuses = ["pending", "downloading", "ready", "in_progress", "completed"]
    stats = {"total_tasks": 0}
    
    for status in statuses:
        count_result = await db.execute(
            select(func.count(Task.id)).where(Task.status == status)
        )
        count = count_result.scalar()
        stats[status] = count
        stats["total_tasks"] += count
    
    return TaskStats(**stats)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific task."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Check access
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )
    
    assignee_name = task.assignee.name if task.assignee else None
    
    return TaskResponse(
        id=str(task.id),
        location_type_id=str(task.location_type_id),
        location_type_name=task.location_type.display_name,
        council=task.council,
        group_field=task.group_field,
        group_value=task.group_value,
        name=task.name or task.council,
        assigned_to=str(task.assigned_to) if task.assigned_to else None,
        assignee_name=assignee_name,
        status=task.status,
        total_locations=task.total_locations,
        completed_locations=task.completed_locations,
        failed_locations=task.failed_locations,
        images_downloaded=task.images_downloaded,
        total_images=task.total_images,
        completion_percentage=task.completion_percentage,
        download_progress=task.download_progress,
        created_at=task.created_at,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at
    )


@router.post("/{task_id}/assign")
async def assign_task(
    task_id: uuid.UUID,
    assignment: TaskAssign,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Assign a task to a labeller."""
    # Get task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Verify labeller exists
    labeller_result = await db.execute(
        select(User).where(User.id == uuid.UUID(assignment.labeller_id))
    )
    labeller = labeller_result.scalar_one_or_none()
    
    if not labeller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Labeller not found"
        )
    
    # Assign task
    task.assigned_to = labeller.id
    task.assigned_at = datetime.utcnow()
    
    # Start image download if not already done
    if task.status == "pending":
        task.status = "downloading"
        # Trigger background download via Celery
        try:
            from app.tasks.celery_tasks import download_task_images_celery
            download_task_images_celery.delay(str(task.id))
        except Exception as e:
            # Fallback to inline background task if Celery unavailable
            print(f"Celery unavailable, using inline task: {e}")
            background_tasks.add_task(download_task_images, str(task.id))
    
    await db.commit()
    
    return {"message": "Task assigned successfully"}


@router.post("/bulk-assign")
async def bulk_assign_tasks(
    assignment: BulkAssign,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Bulk assign multiple tasks to a labeller."""
    # Verify labeller exists
    labeller_result = await db.execute(
        select(User).where(User.id == uuid.UUID(assignment.labeller_id))
    )
    labeller = labeller_result.scalar_one_or_none()
    
    if not labeller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Labeller not found"
        )
    
    assigned_count = 0
    for task_id_str in assignment.task_ids:
        task_id = uuid.UUID(task_id_str)
        result = await db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if task:
            task.assigned_to = labeller.id
            task.assigned_at = datetime.utcnow()
            
            if task.status == "pending":
                task.status = "downloading"
                # Trigger background download via Celery
                try:
                    from app.tasks.celery_tasks import download_task_images_celery
                    download_task_images_celery.delay(str(task.id))
                except Exception as e:
                    # Fallback to inline background task if Celery unavailable
                    background_tasks.add_task(download_task_images, str(task.id))
            
            assigned_count += 1
    
    await db.commit()
    
    return {
        "message": f"Assigned {assigned_count} tasks",
        "assigned_count": assigned_count
    }


@router.post("/{task_id}/start")
async def start_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_labeller)
):
    """Start working on a task."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    if task.assigned_to != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This task is not assigned to you"
        )
    
    if task.status not in ["ready", "in_progress"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start task with status: {task.status}"
        )
    
    if task.status == "ready":
        task.status = "in_progress"
        task.started_at = datetime.utcnow()
        await db.commit()
    
    return {"message": "Task started"}


@router.post("/download-all-images")
async def trigger_all_image_downloads(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Start image download for all pending tasks."""
    from app.models.download_log import DownloadLog
    
    # Get all tasks that need downloading
    result = await db.execute(
        select(Task).where(
            Task.status.in_(["pending", "assigned"])
        )
    )
    tasks = result.scalars().all()
    
    if not tasks:
        return {
            "message": "No pending tasks found",
            "tasks_queued": 0
        }
    
    queued_count = 0
    for task in tasks:
        # Create download log
        download_log = DownloadLog(
            task_id=task.id,
            status="pending",
            total_locations=task.total_locations
        )
        db.add(download_log)
        
        # Update task status
        if task.status == "pending":
            task.status = "downloading"
        
        await db.flush()  # Get the download_log.id
        
        # Queue the download
        try:
            from app.tasks.celery_tasks import download_task_images_celery
            download_task_images_celery.delay(str(task.id), str(download_log.id))
            queued_count += 1
        except Exception as e:
            print(f"Failed to queue download for task {task.id}: {e}")
    
    await db.commit()
    
    return {
        "message": f"Started image download for {queued_count} tasks",
        "tasks_queued": queued_count,
        "total_pending_tasks": len(tasks)
    }


@router.post("/{task_id}/download-images")
async def trigger_image_download(
    task_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Manually trigger image download for a task."""
    from app.models.download_log import DownloadLog
    
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Create download log
    download_log = DownloadLog(
        task_id=task_id,
        status="pending",
        total_locations=task.total_locations
    )
    db.add(download_log)
    
    # Update task status
    if task.status == "pending":
        task.status = "downloading"
    
    await db.commit()
    await db.refresh(download_log)
    
    # Trigger background download via Celery
    try:
        from app.tasks.celery_tasks import download_task_images_celery
        download_task_images_celery.delay(str(task.id), str(download_log.id))
    except Exception as e:
        print(f"Celery unavailable, using inline task: {e}")
        background_tasks.add_task(download_task_images, str(task.id), str(download_log.id))
    
    return {
        "message": "Image download started",
        "task_id": str(task_id),
        "download_log_id": str(download_log.id),
        "total_images": task.total_images
    }


@router.get("/{task_id}/download-logs")
async def get_download_logs(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get download logs for a task."""
    from app.models.download_log import DownloadLog
    import json
    
    result = await db.execute(
        select(DownloadLog)
        .where(DownloadLog.task_id == task_id)
        .order_by(DownloadLog.created_at.desc())
    )
    logs = result.scalars().all()
    
    return {
        "task_id": str(task_id),
        "logs": [
            {
                "id": str(log.id),
                "status": log.status,
                "total_locations": log.total_locations,
                "processed_locations": log.processed_locations,
                "successful_downloads": log.successful_downloads,
                "failed_downloads": log.failed_downloads,
                "skipped_existing": log.skipped_existing,
                "current_location": log.current_location_identifier,
                "last_error": log.last_error,
                "error_count": log.error_count,
                "log_messages": json.loads(log.log_messages) if log.log_messages else [],
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "progress_percent": round((log.processed_locations / log.total_locations * 100) if log.total_locations > 0 else 0, 1)
            }
            for log in logs
        ]
    }


# Global dicts to track download state
_cancelled_downloads: dict = {}
_paused_downloads: dict = {}


@router.post("/{task_id}/cancel-download")
async def cancel_download(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Cancel an ongoing download for a task."""
    from app.models.download_log import DownloadLog
    
    # Mark all in-progress downloads as cancelled
    result = await db.execute(
        select(DownloadLog)
        .where(DownloadLog.task_id == task_id, DownloadLog.status == "in_progress")
    )
    logs = result.scalars().all()
    
    for log in logs:
        log.status = "cancelled"
        log.completed_at = datetime.utcnow()
    
    # Update task status
    task_result = await db.execute(select(Task).where(Task.id == task_id))
    task = task_result.scalar_one_or_none()
    
    if task and task.status == "downloading":
        task.status = "pending"
    
    # Set cancellation flag
    _cancelled_downloads[str(task_id)] = True
    _paused_downloads.pop(str(task_id), None)
    
    await db.commit()
    
    return {"message": "Download cancelled", "task_id": str(task_id)}


@router.post("/{task_id}/pause-download")
async def pause_download(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Pause an ongoing download for a task."""
    from app.models.download_log import DownloadLog
    
    # Mark downloads as paused
    result = await db.execute(
        select(DownloadLog)
        .where(DownloadLog.task_id == task_id, DownloadLog.status == "in_progress")
    )
    logs = result.scalars().all()
    
    for log in logs:
        log.status = "paused"
    
    # Update task status
    task_result = await db.execute(select(Task).where(Task.id == task_id))
    task = task_result.scalar_one_or_none()
    
    if task and task.status == "downloading":
        task.status = "paused"
    
    # Set pause flag
    _paused_downloads[str(task_id)] = True
    
    await db.commit()
    
    return {"message": "Download paused", "task_id": str(task_id)}


@router.post("/{task_id}/resume-download")
async def resume_download(
    task_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Resume a paused download for a task."""
    from app.models.download_log import DownloadLog
    
    task_result = await db.execute(
        select(Task).options(selectinload(Task.location_type)).where(Task.id == task_id)
    )
    task = task_result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Clear pause flag
    _paused_downloads.pop(str(task_id), None)
    _cancelled_downloads.pop(str(task_id), None)
    
    # Update task status
    task.status = "downloading"
    
    # Create or update download log
    download_log = DownloadLog(
        task_id=task_id,
        status="pending",
        total_locations=task.total_locations,
        processed_locations=0,
        successful_downloads=0,
        failed_downloads=0,
        skipped_existing=0
    )
    db.add(download_log)
    await db.commit()
    await db.refresh(download_log)
    
    # Start background download via Celery (will skip already downloaded images)
    try:
        from app.tasks.celery_tasks import download_task_images_celery
        download_task_images_celery.delay(str(task_id), str(download_log.id))
    except Exception as e:
        print(f"Celery unavailable, using inline task: {e}")
        background_tasks.add_task(download_task_images, str(task_id), str(download_log.id))
    
    return {
        "message": "Download resumed",
        "task_id": str(task_id),
        "download_log_id": str(download_log.id)
    }


@router.post("/{task_id}/restart-download")
async def restart_download(
    task_id: uuid.UUID,
    force: bool = False,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Restart download for a task.
    
    Args:
        force: If True, delete existing images and re-download all.
               If False, only download missing images.
    """
    from app.models.download_log import DownloadLog
    from app.models.gsv_image import GSVImage
    
    task_result = await db.execute(
        select(Task).options(selectinload(Task.location_type)).where(Task.id == task_id)
    )
    task = task_result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Clear any pause/cancel flags
    _paused_downloads.pop(str(task_id), None)
    _cancelled_downloads.pop(str(task_id), None)
    
    deleted_count = 0
    if force:
        # Delete existing images for this task's locations
        # First get location IDs for this task
        base_query = select(Location.id).where(Location.location_type_id == task.location_type_id)
        
        if task.group_field and task.group_field.startswith("original_"):
            original_key = task.group_field.replace("original_", "")
            base_query = base_query.where(
                text(f"original_data->>'{original_key}' = :group_value")
            ).params(group_value=task.group_value)
        elif task.group_field == "council" or not task.group_field:
            base_query = base_query.where(Location.council == (task.group_value or task.council))
        
        location_ids_result = await db.execute(base_query)
        location_ids = [row[0] for row in location_ids_result.fetchall()]
        
        if location_ids:
            # Delete images
            delete_result = await db.execute(
                GSVImage.__table__.delete().where(
                    GSVImage.location_id.in_(location_ids),
                    GSVImage.is_user_snapshot == False
                )
            )
            deleted_count = delete_result.rowcount
        
        # Reset task counters
        task.images_downloaded = 0
    
    # Update task status
    task.status = "downloading"
    
    # Create new download log
    download_log = DownloadLog(
        task_id=task_id,
        status="pending",
        total_locations=task.total_locations,
        processed_locations=0,
        successful_downloads=0,
        failed_downloads=0,
        skipped_existing=0
    )
    db.add(download_log)
    await db.commit()
    await db.refresh(download_log)
    
    # Start background download via Celery
    try:
        from app.tasks.celery_tasks import download_task_images_celery
        download_task_images_celery.delay(str(task_id), str(download_log.id))
    except Exception as e:
        print(f"Celery unavailable, using inline task: {e}")
        if background_tasks:
            background_tasks.add_task(download_task_images, str(task_id), str(download_log.id))
    
    return {
        "message": f"Download {'restarted (forced)' if force else 'restarted'}",
        "task_id": str(task_id),
        "download_log_id": str(download_log.id),
        "deleted_images": deleted_count if force else 0
    }


@router.get("/{task_id}/download-status")
async def get_download_status(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get current download status for a task."""
    from app.models.download_log import DownloadLog
    
    task_result = await db.execute(select(Task).where(Task.id == task_id))
    task = task_result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get latest download log
    log_result = await db.execute(
        select(DownloadLog)
        .where(DownloadLog.task_id == task_id)
        .order_by(DownloadLog.created_at.desc())
        .limit(1)
    )
    latest_log = log_result.scalar_one_or_none()
    
    return {
        "task_id": str(task_id),
        "task_status": task.status,
        "images_downloaded": task.images_downloaded or 0,
        "total_locations": task.total_locations,
        "is_paused": str(task_id) in _paused_downloads,
        "is_cancelled": str(task_id) in _cancelled_downloads,
        "latest_log": {
            "id": str(latest_log.id),
            "status": latest_log.status,
            "processed": latest_log.processed_locations,
            "successful": latest_log.successful_downloads,
            "failed": latest_log.failed_downloads,
            "skipped": latest_log.skipped_existing,
            "current_location": latest_log.current_location_identifier,
            "started_at": latest_log.started_at.isoformat() if latest_log.started_at else None,
        } if latest_log else None
    }


@router.get("/{task_id}/images")
async def get_task_images(
    task_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get downloaded images for a task."""
    from app.models.gsv_image import GSVImage
    
    result = await db.execute(
        select(Task).options(selectinload(Task.location_type)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Build query to get locations for this task
    base_query = select(Location).where(Location.location_type_id == task.location_type_id)
    
    if task.group_field and task.group_field.startswith("original_"):
        original_key = task.group_field.replace("original_", "")
        base_query = base_query.where(
            text(f"original_data->>'{original_key}' = :group_value")
        ).params(group_value=task.group_value)
    elif task.group_field == "council" or not task.group_field:
        base_query = base_query.where(Location.council == (task.group_value or task.council))
    elif task.group_field == "combined_authority":
        base_query = base_query.where(Location.combined_authority == task.group_value)
    elif task.group_field == "road_classification":
        base_query = base_query.where(Location.road_classification == task.group_value)
    
    # Get total count
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total_locations = count_result.scalar()
    
    # Get paginated locations
    offset = (page - 1) * page_size
    locations_result = await db.execute(
        base_query.order_by(Location.identifier).offset(offset).limit(page_size)
    )
    locations = locations_result.scalars().all()
    
    # Get images for these locations
    location_ids = [loc.id for loc in locations]
    images_result = await db.execute(
        select(GSVImage).where(GSVImage.location_id.in_(location_ids))
    )
    images = images_result.scalars().all()
    
    # Group images by location
    images_by_location = {}
    for img in images:
        loc_id = str(img.location_id)
        if loc_id not in images_by_location:
            images_by_location[loc_id] = []
        # Normalize URL - strip localhost:8000 if present for relative URLs
        gcs_url = img.gcs_url
        if gcs_url and gcs_url.startswith("http://localhost:8000"):
            gcs_url = gcs_url.replace("http://localhost:8000", "")
        images_by_location[loc_id].append({
            "id": str(img.id),
            "heading": img.heading,
            "gcs_url": gcs_url,
            "capture_date": img.capture_date.isoformat() if img.capture_date else None,
            "is_user_snapshot": img.is_user_snapshot
        })
    
    return {
        "task_id": str(task_id),
        "task_name": task.name or task.group_value or task.council,
        "locations": [
            {
                "id": str(loc.id),
                "identifier": loc.identifier,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "images": images_by_location.get(str(loc.id), []),
                "has_images": len(images_by_location.get(str(loc.id), [])) > 0
            }
            for loc in locations
        ],
        "page": page,
        "page_size": page_size,
        "total_locations": total_locations,
        "total_pages": (total_locations + page_size - 1) // page_size,
        "download_progress": task.download_progress,
        "images_downloaded": task.images_downloaded,
        "total_images": task.total_images
    }


async def download_task_images(task_id: str, download_log_id: str = None):
    """Background task to download GSV images for a task."""
    from app.core.database import async_session_maker
    from app.models.gsv_image import GSVImage
    from app.models.download_log import DownloadLog
    from app.services.gsv_downloader import GSVDownloader
    from app.core.config import settings
    import json
    import traceback
    
    print(f"[GSV Download] Starting download for task {task_id}")
    
    async with async_session_maker() as db:
        # Get download log if provided
        download_log = None
        if download_log_id:
            log_result = await db.execute(
                select(DownloadLog).where(DownloadLog.id == uuid.UUID(download_log_id))
            )
            download_log = log_result.scalar_one_or_none()
        
        def add_log_message(message: str, level: str = "info"):
            """Add a message to the download log."""
            print(f"[GSV Download] [{level.upper()}] {message}")
            if download_log:
                try:
                    messages = json.loads(download_log.log_messages or "[]")
                    messages.append({
                        "time": datetime.utcnow().isoformat(),
                        "level": level,
                        "message": message
                    })
                    # Keep only last 100 messages
                    if len(messages) > 100:
                        messages = messages[-100:]
                    download_log.log_messages = json.dumps(messages)
                except:
                    pass
        
        try:
            # Get task
            result = await db.execute(
                select(Task).options(selectinload(Task.location_type)).where(Task.id == uuid.UUID(task_id))
            )
            task = result.scalar_one_or_none()
            
            if not task:
                add_log_message(f"Task {task_id} not found", "error")
                if download_log:
                    download_log.status = "failed"
                    download_log.last_error = "Task not found"
                    await db.commit()
                return
            
            # Check GSV API key
            if not settings.GSV_API_KEY:
                add_log_message("GSV_API_KEY is not configured!", "error")
                if download_log:
                    download_log.status = "failed"
                    download_log.last_error = "GSV_API_KEY is not configured. Please set it in the environment."
                    await db.commit()
                task.status = "pending"  # Revert status
                await db.commit()
                return
            
            add_log_message(f"GSV API Key configured: {settings.GSV_API_KEY[:10]}...")
            
            if download_log:
                download_log.status = "in_progress"
                download_log.started_at = datetime.utcnow()
                await db.commit()
            
            # Build query to get locations for this task
            base_query = select(Location).where(Location.location_type_id == task.location_type_id)
            
            if task.group_field and task.group_field.startswith("original_"):
                original_key = task.group_field.replace("original_", "")
                base_query = base_query.where(
                    text(f"original_data->>'{original_key}' = :group_value")
                ).params(group_value=task.group_value)
            elif task.group_field == "council" or not task.group_field:
                base_query = base_query.where(Location.council == (task.group_value or task.council))
            elif task.group_field == "combined_authority":
                base_query = base_query.where(Location.combined_authority == task.group_value)
            elif task.group_field == "road_classification":
                base_query = base_query.where(Location.road_classification == task.group_value)
            
            # Get all locations
            locations_result = await db.execute(base_query.order_by(Location.identifier))
            locations = locations_result.scalars().all()
            
            total_locations = len(locations)
            add_log_message(f"Found {total_locations} locations to process")
            
            if download_log:
                download_log.total_locations = total_locations
                await db.commit()
            
            # Initialize downloader
            downloader = GSVDownloader()
            
            images_downloaded = 0
            skipped_existing = 0
            failed_downloads = 0
            processed = 0
            
            for location in locations:
                # Check for cancellation
                if _cancelled_downloads.get(task_id):
                    add_log_message("Download cancelled by user", "warning")
                    if download_log:
                        download_log.status = "cancelled"
                        download_log.completed_at = datetime.utcnow()
                    task.status = "pending"
                    await db.commit()
                    _cancelled_downloads.pop(task_id, None)
                    return
                
                # Check for pause
                if _paused_downloads.get(task_id):
                    add_log_message("Download paused by user", "warning")
                    if download_log:
                        download_log.status = "paused"
                    task.status = "paused"
                    await db.commit()
                    return
                
                processed += 1
                
                if download_log:
                    download_log.processed_locations = processed
                    download_log.current_location_id = location.id
                    download_log.current_location_identifier = location.identifier
                
                # Check if images already exist for this location
                existing_result = await db.execute(
                    select(func.count(GSVImage.id)).where(
                        GSVImage.location_id == location.id,
                        GSVImage.is_user_snapshot == False
                    )
                )
                existing_count = existing_result.scalar()
                
                if existing_count >= 4:
                    # Already has all 4 images
                    images_downloaded += existing_count
                    skipped_existing += 1
                    if download_log:
                        download_log.skipped_existing = skipped_existing
                    if processed % 50 == 0:
                        add_log_message(f"Progress: {processed}/{total_locations} - Skipped {location.identifier} (already has {existing_count} images)")
                    continue
                
                # Download images for this location
                try:
                    add_log_message(f"Downloading images for {location.identifier} ({location.latitude}, {location.longitude})")
                    
                    # Get location type name and council for organized storage
                    location_type_name = task.location_type.display_name if task.location_type else "unspecified"
                    location_council = location.council or task.group_value or "unspecified"
                    
                    downloaded = await downloader.download_images_for_location(
                        db=db,
                        location_id=location.id,
                        latitude=location.latitude,
                        longitude=location.longitude,
                        identifier=location.identifier,
                        location_type=location_type_name,
                        council=location_council
                    )
                    images_downloaded += downloaded
                    
                    if download_log:
                        download_log.successful_downloads += downloaded
                    
                    add_log_message(f"Downloaded {downloaded} images for {location.identifier}")
                    
                except Exception as e:
                    error_msg = f"Error downloading images for {location.identifier}: {str(e)}"
                    add_log_message(error_msg, "error")
                    failed_downloads += 1
                    
                    if download_log:
                        download_log.failed_downloads = failed_downloads
                        download_log.last_error = str(e)
                        download_log.error_count += 1
                
                # Update progress periodically
                task.images_downloaded = images_downloaded
                await db.commit()
                
                # Log progress every 10 locations
                if processed % 10 == 0:
                    add_log_message(f"Progress: {processed}/{total_locations} locations, {images_downloaded} images downloaded, {failed_downloads} failed")
            
            # Mark task as ready
            task.images_downloaded = images_downloaded
            if task.status == "downloading":
                task.status = "ready"
            
            if download_log:
                download_log.status = "completed"
                download_log.completed_at = datetime.utcnow()
                download_log.current_location_id = None
                download_log.current_location_identifier = None
            
            await db.commit()
            
            add_log_message(f"Download complete! {images_downloaded} images downloaded, {skipped_existing} skipped (existing), {failed_downloads} failed")
            
        except Exception as e:
            error_msg = f"Fatal error in download task: {str(e)}\n{traceback.format_exc()}"
            print(f"[GSV Download] [ERROR] {error_msg}")
            
            if download_log:
                download_log.status = "failed"
                download_log.last_error = str(e)
                download_log.completed_at = datetime.utcnow()
                await db.commit()


class CreateSampleTaskRequest(BaseModel):
    """Request to create a sample task."""
    source_task_id: str
    sample_size: int  # Number of locations to include
    sample_name: Optional[str] = None


class SampleTaskResponse(BaseModel):
    """Response for sample task creation."""
    task_id: str
    name: str
    sample_size: int
    source_task_name: str
    message: str


@router.post("/sample", response_model=SampleTaskResponse)
async def create_sample_task(
    request: CreateSampleTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Create a sample task from an existing task with downloaded images.
    
    This creates a new task with a random subset of locations from the source task.
    Useful for creating training/demo datasets.
    """
    import random
    from app.models.gsv_image import GSVImage
    
    # Get source task
    source_result = await db.execute(
        select(Task)
        .options(selectinload(Task.location_type))
        .where(Task.id == uuid.UUID(request.source_task_id))
    )
    source_task = source_result.scalar_one_or_none()
    
    if not source_task:
        raise HTTPException(status_code=404, detail="Source task not found")
    
    # Check if source task has downloaded images
    if source_task.images_downloaded == 0:
        raise HTTPException(
            status_code=400,
            detail="Source task has no downloaded images. Please download images first."
        )
    
    # Get locations for the source task that have images
    if source_task.is_sample and source_task.sample_location_ids:
        # Source is also a sample task - get those specific locations
        location_query = (
            select(Location.id)
            .where(Location.id.in_([uuid.UUID(lid) for lid in source_task.sample_location_ids]))
        )
    else:
        # Regular task - get locations by group field
        if source_task.group_field and source_task.group_value:
            if source_task.group_field == "council":
                location_query = (
                    select(Location.id)
                    .where(
                        Location.location_type_id == source_task.location_type_id,
                        Location.council == source_task.group_value
                    )
                )
            elif source_task.group_field == "combined_authority":
                location_query = (
                    select(Location.id)
                    .where(
                        Location.location_type_id == source_task.location_type_id,
                        Location.combined_authority == source_task.group_value
                    )
                )
            else:
                # Fall back to council field
                location_query = (
                    select(Location.id)
                    .where(
                        Location.location_type_id == source_task.location_type_id,
                        Location.council == source_task.council
                    )
                )
        else:
            location_query = (
                select(Location.id)
                .where(
                    Location.location_type_id == source_task.location_type_id,
                    Location.council == source_task.council
                )
            )
    
    # Filter to only locations with images
    location_query = (
        location_query
        .where(
            Location.id.in_(
                select(GSVImage.location_id).distinct()
            )
        )
    )
    
    result = await db.execute(location_query)
    location_ids = [str(row[0]) for row in result.fetchall()]
    
    if len(location_ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="No locations with images found in source task"
        )
    
    # Validate sample size
    if request.sample_size <= 0:
        raise HTTPException(status_code=400, detail="Sample size must be positive")
    
    if request.sample_size > len(location_ids):
        raise HTTPException(
            status_code=400,
            detail=f"Sample size ({request.sample_size}) exceeds available locations with images ({len(location_ids)})"
        )
    
    # Random sample
    sampled_ids = random.sample(location_ids, request.sample_size)
    
    # Create sample task name
    source_name = source_task.name or source_task.group_value or source_task.council
    sample_name = request.sample_name or f"Sample: {source_name} ({request.sample_size} locations)"
    
    # Create the sample task
    sample_task = Task(
        location_type_id=source_task.location_type_id,
        council=source_task.council,
        group_field=source_task.group_field,
        group_value=source_task.group_value,
        name=sample_name,
        status="ready",  # Sample tasks are immediately ready
        total_locations=request.sample_size,
        images_downloaded=request.sample_size * 5,  # Assume 5 images per location
        total_images=request.sample_size * 5,
        is_sample=True,
        source_task_id=source_task.id,
        sample_location_ids=sampled_ids
    )
    
    db.add(sample_task)
    await db.commit()
    await db.refresh(sample_task)
    
    return SampleTaskResponse(
        task_id=str(sample_task.id),
        name=sample_name,
        sample_size=request.sample_size,
        source_task_name=source_name,
        message=f"Created sample task with {request.sample_size} locations from '{source_name}'"
    )


@router.get("/with-images", response_model=List[TaskResponse])
async def get_tasks_with_images(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get all tasks that have downloaded images (for sample task creation)."""
    result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.location_type),
            selectinload(Task.assignee)
        )
        .where(Task.images_downloaded > 0)
        .order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    
    return [
        TaskResponse(
            id=str(t.id),
            location_type_id=str(t.location_type_id),
            location_type_name=t.location_type.display_name if t.location_type else "Unknown",
            council=t.council,
            group_field=t.group_field,
            group_value=t.group_value,
            name=t.name,
            assigned_to=str(t.assigned_to) if t.assigned_to else None,
            assignee_name=t.assignee.name if t.assignee else None,
            status=t.status,
            total_locations=t.total_locations,
            completed_locations=t.completed_locations,
            failed_locations=t.failed_locations,
            images_downloaded=t.images_downloaded,
            total_images=t.total_images,
            completion_percentage=t.completion_percentage,
            download_progress=t.download_progress,
            created_at=t.created_at,
            assigned_at=t.assigned_at,
            started_at=t.started_at,
            completed_at=t.completed_at
        )
        for t in tasks
    ]

