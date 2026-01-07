"""Labelling routes for the labelling interface."""
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.location import Location, LocationType
from app.models.task import Task
from app.models.label import Label
from app.models.gsv_image import GSVImage
from app.api.deps import get_current_user, require_labeller, require_manager
from app.services.gcs_storage import GCSStorage


router = APIRouter(prefix="/labelling", tags=["Labelling"])


class LabelData(BaseModel):
    """Label data for saving."""
    advertising_present: Optional[bool] = None
    bus_shelter_present: Optional[bool] = None
    number_of_panels: Optional[int] = None
    pole_stop: Optional[bool] = None
    unmarked_stop: Optional[bool] = None
    selected_image: Optional[int] = None
    notes: Optional[str] = None
    custom_fields: Optional[dict] = None
    unable_to_label: bool = False
    unable_reason: Optional[str] = None


class LocationLabelResponse(BaseModel):
    """Location with label data for labelling view."""
    id: str
    identifier: str
    latitude: float
    longitude: float
    council: Optional[str]
    road_name: Optional[str]
    locality: Optional[str]
    road_classification: Optional[str]
    combined_authority: Optional[str]
    original_data: Optional[dict]
    index: int
    total: int
    images: List[dict]
    label: Optional[dict]
    label_fields: dict


class LabelSaveResponse(BaseModel):
    """Response after saving a label."""
    message: str
    completed: int
    total: int
    is_task_complete: bool


class SnapshotResponse(BaseModel):
    """Response after saving a snapshot."""
    id: str
    gcs_url: str
    heading: int
    capture_date: Optional[str]


class SnapshotRequest(BaseModel):
    """Request to save a snapshot from GSV."""
    heading: int
    pitch: int = 0
    pano_id: Optional[str] = None


@router.get("/task/{task_id}/locations")
async def get_task_locations(
    task_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get paginated list of locations for a task."""
    # Get task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access - labellers can only access assigned tasks, managers can access all
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query based on task's group_field
    offset = (page - 1) * page_size
    base_query = select(Location).where(Location.location_type_id == task.location_type_id)
    
    # Filter by the task's grouping
    if task.group_field and task.group_field.startswith("original_"):
        # Filter by original_data JSONB field
        original_key = task.group_field.replace("original_", "")
        from sqlalchemy import text
        base_query = base_query.where(
            text(f"original_data->>'{original_key}' = :group_value")
        ).params(group_value=task.group_value)
    elif task.group_field == "council" or not task.group_field:
        base_query = base_query.where(Location.council == (task.group_value or task.council))
    elif task.group_field == "combined_authority":
        base_query = base_query.where(Location.combined_authority == task.group_value)
    elif task.group_field == "road_classification":
        base_query = base_query.where(Location.road_classification == task.group_value)
    
    locations_result = await db.execute(
        base_query.offset(offset).limit(page_size).order_by(Location.identifier)
    )
    locations = locations_result.scalars().all()
    
    # Get labels for these locations
    location_ids = [loc.id for loc in locations]
    labels_result = await db.execute(
        select(Label).where(
            Label.task_id == task_id,
            Label.location_id.in_(location_ids)
        )
    )
    labels = {str(l.location_id): l for l in labels_result.scalars().all()}
    
    return {
        "locations": [
            {
                "id": str(loc.id),
                "identifier": loc.identifier,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "has_label": str(loc.id) in labels,
                "label_status": labels.get(str(loc.id), {}).status if str(loc.id) in labels else None
            }
            for loc in locations
        ],
        "page": page,
        "page_size": page_size,
        "total": task.total_locations
    }


@router.get("/task/{task_id}/location/{location_index}", response_model=LocationLabelResponse)
async def get_location_for_labelling(
    task_id: uuid.UUID,
    location_index: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific location for labelling by index."""
    from sqlalchemy.orm import selectinload
    
    # Get task with location_type eagerly loaded
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.location_type))
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access - labellers can only access assigned tasks, managers can access all
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query based on task's group_field
    base_query = select(Location).where(Location.location_type_id == task.location_type_id)
    
    # Filter by the task's grouping
    if task.group_field and task.group_field.startswith("original_"):
        original_key = task.group_field.replace("original_", "")
        from sqlalchemy import text
        base_query = base_query.where(
            text(f"original_data->>'{original_key}' = :group_value")
        ).params(group_value=task.group_value)
    elif task.group_field == "council" or not task.group_field:
        base_query = base_query.where(Location.council == (task.group_value or task.council))
    elif task.group_field == "combined_authority":
        base_query = base_query.where(Location.combined_authority == task.group_value)
    elif task.group_field == "road_classification":
        base_query = base_query.where(Location.road_classification == task.group_value)
    
    # Get location by index
    location_result = await db.execute(
        base_query.order_by(Location.identifier).offset(location_index).limit(1)
    )
    location = location_result.scalar_one_or_none()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    # Get images for this location
    images_result = await db.execute(
        select(GSVImage)
        .where(GSVImage.location_id == location.id)
        .order_by(GSVImage.heading)
    )
    images = images_result.scalars().all()
    
    # Get existing label
    label_result = await db.execute(
        select(Label).where(
            Label.task_id == task_id,
            Label.location_id == location.id
        )
    )
    label = label_result.scalar_one_or_none()
    
    # Get label fields from location type
    label_fields = task.location_type.label_fields
    
    # Extract additional fields from original_data
    original_data = location.original_data or {}
    road_name = original_data.get('LocalityName') or original_data.get('RoadName') or original_data.get('road_name')
    locality = original_data.get('LocalityName') or original_data.get('Locality') or original_data.get('locality')
    
    return LocationLabelResponse(
        id=str(location.id),
        identifier=location.identifier,
        latitude=location.latitude,
        longitude=location.longitude,
        council=location.council,
        road_name=road_name,
        locality=locality,
        road_classification=location.road_classification,
        combined_authority=location.combined_authority,
        original_data=original_data,
        index=location_index,
        total=task.total_locations,
        images=[
            {
                "id": str(img.id),
                "heading": img.heading,
                # Normalize URL - strip localhost:8000 if present for relative URLs
                "gcs_url": img.gcs_url.replace("http://localhost:8000", "") if img.gcs_url and img.gcs_url.startswith("http://localhost:8000") else img.gcs_url,
                "capture_date": img.capture_date.isoformat() if img.capture_date else None,
                "is_user_snapshot": img.is_user_snapshot
            }
            for img in images
        ],
        label={
            "advertising_present": label.advertising_present,
            "bus_shelter_present": label.bus_shelter_present,
            "number_of_panels": label.number_of_panels,
            "pole_stop": label.pole_stop,
            "unmarked_stop": label.unmarked_stop,
            "selected_image": label.selected_image,
            "notes": label.notes,
            "custom_fields": label.custom_fields,
            "unable_to_label": label.unable_to_label,
            "unable_reason": label.unable_reason
        } if label else None,
        label_fields=label_fields
    )


@router.get("/task/{task_id}/search")
async def search_location(
    task_id: uuid.UUID,
    query: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for a location by identifier within a task."""
    # Get task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access - labellers can only access assigned tasks, managers can access all
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build base query with task grouping
    from sqlalchemy import text
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
    
    # Search by identifier within task scope
    search_result = await db.execute(
        base_query.where(Location.identifier.ilike(f"%{query}%")).limit(20)
    )
    locations = search_result.scalars().all()
    
    # Get indices for found locations
    results = []
    for loc in locations:
        # Build count query for index with same grouping
        count_query = select(func.count(Location.id)).where(
            Location.location_type_id == task.location_type_id,
            Location.identifier < loc.identifier
        )
        
        if task.group_field and task.group_field.startswith("original_"):
            original_key = task.group_field.replace("original_", "")
            count_query = count_query.where(
                text(f"original_data->>'{original_key}' = :group_value")
            ).params(group_value=task.group_value)
        elif task.group_field == "council" or not task.group_field:
            count_query = count_query.where(Location.council == (task.group_value or task.council))
        elif task.group_field == "combined_authority":
            count_query = count_query.where(Location.combined_authority == task.group_value)
        elif task.group_field == "road_classification":
            count_query = count_query.where(Location.road_classification == task.group_value)
        
        index_result = await db.execute(count_query)
        index = index_result.scalar()
        
        results.append({
            "id": str(loc.id),
            "identifier": loc.identifier,
            "index": index
        })
    
    return {"results": results}


@router.post("/task/{task_id}/location/{location_id}/label", response_model=LabelSaveResponse)
async def save_label(
    task_id: uuid.UUID,
    location_id: uuid.UUID,
    label_data: LabelData,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_labeller)
):
    """Save a label for a location."""
    # Get task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get or create label
    label_result = await db.execute(
        select(Label).where(
            Label.task_id == task_id,
            Label.location_id == location_id
        )
    )
    label = label_result.scalar_one_or_none()
    
    is_new = label is None
    
    if is_new:
        label = Label(
            location_id=location_id,
            task_id=task_id,
            labeller_id=current_user.id,
            labelling_started_at=datetime.utcnow()
        )
        db.add(label)
    
    # Update label data
    label.advertising_present = label_data.advertising_present
    label.bus_shelter_present = label_data.bus_shelter_present
    label.number_of_panels = label_data.number_of_panels
    label.pole_stop = label_data.pole_stop
    label.unmarked_stop = label_data.unmarked_stop
    label.selected_image = label_data.selected_image
    label.notes = label_data.notes
    label.custom_fields = label_data.custom_fields or {}
    label.unable_to_label = label_data.unable_to_label
    label.unable_reason = label_data.unable_reason
    label.status = "completed"
    label.labelling_completed_at = datetime.utcnow()
    
    # Update task progress
    if is_new:
        if label_data.unable_to_label:
            task.failed_locations += 1
        else:
            task.completed_locations += 1
    
    # Check if task is complete
    is_task_complete = (task.completed_locations + task.failed_locations) >= task.total_locations
    if is_task_complete:
        task.status = "completed"
        task.completed_at = datetime.utcnow()
    
    await db.commit()
    
    return LabelSaveResponse(
        message="Label saved successfully",
        completed=task.completed_locations + task.failed_locations,
        total=task.total_locations,
        is_task_complete=is_task_complete
    )


@router.post("/task/{task_id}/location/{location_id}/snapshot", response_model=SnapshotResponse)
async def save_snapshot(
    task_id: uuid.UUID,
    location_id: uuid.UUID,
    snapshot_data: SnapshotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_labeller)
):
    """Save a user-created snapshot from GSV embed using Street View Static API."""
    import httpx
    from app.core.config import settings
    
    # Get task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get location
    loc_result = await db.execute(
        select(Location).where(Location.id == location_id)
    )
    location = loc_result.scalar_one_or_none()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    # Fetch image from Street View Static API
    gsv_api_key = settings.GSV_API_KEY
    if not gsv_api_key:
        raise HTTPException(status_code=500, detail="GSV API key not configured")
    
    # Build Street View Static API URL
    params = {
        "size": "640x480",
        "heading": snapshot_data.heading,
        "pitch": snapshot_data.pitch,
        "fov": 90,
        "key": gsv_api_key
    }
    
    # Use pano_id if available, otherwise use coordinates
    if snapshot_data.pano_id:
        params["pano"] = snapshot_data.pano_id
    else:
        params["location"] = f"{location.latitude},{location.longitude}"
    
    # Fetch the image
    async with httpx.AsyncClient() as client:
        gsv_url = "https://maps.googleapis.com/maps/api/streetview"
        response = await client.get(gsv_url, params=params)
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch Street View image")
        
        image_content = response.content
    
    # Upload to storage
    storage = GCSStorage()
    filename = f"snapshots/{location.identifier}_snapshot_{snapshot_data.heading}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
    gcs_url = await storage.upload_file(image_content, filename, "image/jpeg")
    
    # Save image record
    from datetime import date
    gsv_image = GSVImage(
        location_id=location_id,
        heading=snapshot_data.heading,
        pitch=snapshot_data.pitch,
        gcs_path=filename,
        gcs_url=gcs_url,
        pano_id=snapshot_data.pano_id,
        capture_date=date.today(),
        is_user_snapshot=True,
        snapshot_by=current_user.id
    )
    db.add(gsv_image)
    await db.commit()
    await db.refresh(gsv_image)
    
    return SnapshotResponse(
        id=str(gsv_image.id),
        gcs_url=gcs_url,
        heading=snapshot_data.heading,
        capture_date=date.today().isoformat()
    )


@router.get("/task/{task_id}/progress")
async def get_labelling_progress(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_labeller)
):
    """Get detailed labelling progress for a task."""
    # Get task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role == "labeller" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get label statistics
    labels_result = await db.execute(
        select(
            func.count(Label.id).label("total"),
            func.sum(func.cast(Label.advertising_present == True, Integer)).label("with_advertising"),
            func.sum(func.cast(Label.unable_to_label == True, Integer)).label("unable")
        )
        .where(Label.task_id == task_id)
    )
    stats = labels_result.one()
    
    return {
        "task_id": str(task_id),
        "total_locations": task.total_locations,
        "completed": task.completed_locations,
        "failed": task.failed_locations,
        "remaining": task.total_locations - task.completed_locations - task.failed_locations,
        "completion_percentage": task.completion_percentage,
        "with_advertising": stats.with_advertising or 0,
        "unable_to_label": stats.unable or 0
    }


# Import Integer for the query
from sqlalchemy import Integer

