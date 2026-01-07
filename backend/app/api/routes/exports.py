"""Export routes for CSV and ZIP downloads."""
import uuid
import io
import zipfile
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pandas as pd

from app.core.database import get_db
from app.models.user import User
from app.models.location import Location, LocationType
from app.models.task import Task
from app.models.label import Label
from app.models.gsv_image import GSVImage
from app.api.deps import require_manager
from app.services.gcs_storage import GCSStorage


router = APIRouter(prefix="/exports", tags=["Exports"])


@router.get("/csv/{location_type_id}")
async def export_csv(
    location_type_id: uuid.UUID,
    council: Optional[str] = None,
    include_unlabelled: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Export labelling results as CSV."""
    # Get location type
    type_result = await db.execute(
        select(LocationType).where(LocationType.id == location_type_id)
    )
    location_type = type_result.scalar_one_or_none()
    
    if not location_type:
        raise HTTPException(status_code=404, detail="Location type not found")
    
    # Build query
    query = (
        select(Location, Label, GSVImage)
        .outerjoin(Label, Label.location_id == Location.id)
        .outerjoin(GSVImage, GSVImage.location_id == Location.id)
        .where(Location.location_type_id == location_type_id)
    )
    
    if council:
        query = query.where(Location.council == council)
    
    if not include_unlabelled:
        query = query.where(Label.id.isnot(None))
    
    result = await db.execute(query)
    rows = result.all()
    
    # Group by location
    locations_data = {}
    for loc, label, image in rows:
        loc_id = str(loc.id)
        if loc_id not in locations_data:
            locations_data[loc_id] = {
                "identifier": loc.identifier,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "council": loc.council,
                "combined_authority": loc.combined_authority,
                "road_classification": loc.road_classification,
                "advertising_present": label.advertising_present if label else None,
                "bus_shelter_present": label.bus_shelter_present if label else None,
                "number_of_panels": label.number_of_panels if label else None,
                "pole_stop": label.pole_stop if label else None,
                "unmarked_stop": label.unmarked_stop if label else None,
                "selected_image": label.selected_image if label else None,
                "notes": label.notes if label else None,
                "unable_to_label": label.unable_to_label if label else None,
                "unable_reason": label.unable_reason if label else None,
                "image_0_url": None,
                "image_90_url": None,
                "image_180_url": None,
                "image_270_url": None,
                "snapshot_url": None,
            }
        
        # Add image URLs
        if image:
            if image.is_user_snapshot:
                locations_data[loc_id]["snapshot_url"] = image.gcs_url
            else:
                locations_data[loc_id][f"image_{image.heading}_url"] = image.gcs_url
    
    # Create DataFrame
    df = pd.DataFrame(list(locations_data.values()))
    
    # Create CSV response
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    filename = f"{location_type.name}"
    if council:
        filename += f"_{council}"
    filename += f"_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/images/{location_type_id}")
async def export_images_zip(
    location_type_id: uuid.UUID,
    council: Optional[str] = None,
    only_with_advertising: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Export images as ZIP file."""
    # Get location type
    type_result = await db.execute(
        select(LocationType).where(LocationType.id == location_type_id)
    )
    location_type = type_result.scalar_one_or_none()
    
    if not location_type:
        raise HTTPException(status_code=404, detail="Location type not found")
    
    # Build query
    query = (
        select(Location, Label, GSVImage)
        .join(Label, Label.location_id == Location.id)
        .join(GSVImage, GSVImage.location_id == Location.id)
        .where(Location.location_type_id == location_type_id)
    )
    
    if council:
        query = query.where(Location.council == council)
    
    if only_with_advertising:
        query = query.where(Label.advertising_present == True)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Download and zip images
    storage = GCSStorage()
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        processed_images = set()
        
        for loc, label, image in rows:
            if str(image.id) in processed_images:
                continue
            
            processed_images.add(str(image.id))
            
            # Download image from GCS
            try:
                image_data = await storage.download_file(image.gcs_path)
                
                # Create folder structure
                folder = loc.council or "unknown"
                if image.is_user_snapshot:
                    filename = f"{folder}/{loc.identifier}_snapshot.jpg"
                else:
                    filename = f"{folder}/{loc.identifier}_{image.heading}.jpg"
                
                zip_file.writestr(filename, image_data)
            except Exception as e:
                print(f"Error downloading image {image.id}: {e}")
                continue
    
    zip_buffer.seek(0)
    
    filename = f"{location_type.name}_images"
    if council:
        filename += f"_{council}"
    filename += f"_{datetime.utcnow().strftime('%Y%m%d')}.zip"
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/task/{task_id}/summary")
async def get_task_summary(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get summary of a task (works even if in progress)."""
    from sqlalchemy.orm import selectinload
    
    # Get task with location type
    result = await db.execute(
        select(Task).options(selectinload(Task.location_type)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get label statistics
    labels_result = await db.execute(
        select(Label).where(Label.task_id == task_id)
    )
    labels = labels_result.scalars().all()
    
    total_labelled = len(labels)
    with_advertising = sum(1 for l in labels if l.advertising_present)
    with_shelter = sum(1 for l in labels if l.bus_shelter_present)
    unable_count = sum(1 for l in labels if l.unable_to_label)
    
    # Calculate panel statistics
    panels = [l.number_of_panels for l in labels if l.number_of_panels is not None]
    avg_panels = sum(panels) / len(panels) if panels else 0
    
    # Calculate time statistics
    durations = [l.labelling_duration_seconds for l in labels if l.labelling_duration_seconds]
    avg_time = sum(durations) / len(durations) if durations else 0
    
    return {
        "task_id": str(task_id),
        "task_name": task.name or task.group_value or task.council,
        "location_type": task.location_type.display_name if task.location_type else "Unknown",
        "council": task.council,
        "group_field": task.group_field,
        "group_value": task.group_value,
        "total_locations": task.total_locations,
        "total_labelled": total_labelled,
        "completion_percent": round((total_labelled / task.total_locations * 100) if task.total_locations > 0 else 0, 1),
        "with_advertising": with_advertising,
        "with_shelter": with_shelter,
        "unable_to_label": unable_count,
        "advertising_rate": round(with_advertising / total_labelled * 100 if total_labelled > 0 else 0, 1),
        "average_panels": round(avg_panels, 1),
        "average_labelling_time_seconds": round(avg_time, 1),
        "status": task.status,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None
    }


@router.get("/task/{task_id}/csv")
async def export_task_csv(
    task_id: uuid.UUID,
    include_unlabelled: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Export labelling results for a specific task as CSV.
    Works even if the task is still in progress.
    """
    from sqlalchemy.orm import selectinload
    from sqlalchemy import text
    
    # Get task with location type
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
    
    # Get all locations
    locations_result = await db.execute(base_query.order_by(Location.identifier))
    locations = locations_result.scalars().all()
    
    # Get all labels for this task
    labels_result = await db.execute(
        select(Label).where(Label.task_id == task_id)
    )
    labels_by_location = {str(l.location_id): l for l in labels_result.scalars().all()}
    
    # Get all images for these locations
    location_ids = [loc.id for loc in locations]
    images_result = await db.execute(
        select(GSVImage).where(GSVImage.location_id.in_(location_ids))
    )
    images_by_location = {}
    for img in images_result.scalars().all():
        loc_id = str(img.location_id)
        if loc_id not in images_by_location:
            images_by_location[loc_id] = {}
        if img.is_user_snapshot:
            images_by_location[loc_id]["snapshot_url"] = img.gcs_url
        else:
            images_by_location[loc_id][f"image_{img.heading}_url"] = img.gcs_url
    
    # Build export data
    export_data = []
    for loc in locations:
        loc_id = str(loc.id)
        label = labels_by_location.get(loc_id)
        images = images_by_location.get(loc_id, {})
        
        # Skip unlabelled if requested
        if not include_unlabelled and not label:
            continue
        
        # Get original data fields
        original_data = loc.original_data or {}
        
        row = {
            "identifier": loc.identifier,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "council": loc.council,
            "combined_authority": loc.combined_authority,
            "road_classification": loc.road_classification,
            "locality": original_data.get("LocalityName") or original_data.get("Locality"),
            "road_name": original_data.get("CommonName") or original_data.get("RoadName"),
            # Label fields
            "labelled": "Yes" if label else "No",
            "advertising_present": label.advertising_present if label else None,
            "bus_shelter_present": label.bus_shelter_present if label else None,
            "number_of_panels": label.number_of_panels if label else None,
            "pole_stop": label.pole_stop if label else None,
            "unmarked_stop": label.unmarked_stop if label else None,
            "selected_image": label.selected_image if label else None,
            "notes": label.notes if label else None,
            "unable_to_label": label.unable_to_label if label else None,
            "unable_reason": label.unable_reason if label else None,
            "labelled_at": label.labelling_completed_at.isoformat() if label and label.labelling_completed_at else None,
            # Image URLs
            "image_0_url": images.get("image_0_url"),
            "image_90_url": images.get("image_90_url"),
            "image_180_url": images.get("image_180_url"),
            "image_270_url": images.get("image_270_url"),
            "snapshot_url": images.get("snapshot_url"),
        }
        export_data.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(export_data)
    
    # Create CSV response
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    # Generate filename
    task_name = task.name or task.group_value or task.council or "task"
    task_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_name)
    status_suffix = f"_{task.status}" if task.status != "completed" else ""
    filename = f"{task_name}{status_suffix}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/task/{task_id}/snapshots")
async def get_task_snapshots(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get all user snapshots for a task."""
    from sqlalchemy.orm import selectinload
    from sqlalchemy import text
    
    # Get task
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
    
    # Get all locations
    locations_result = await db.execute(base_query)
    locations = locations_result.scalars().all()
    location_ids = [loc.id for loc in locations]
    locations_by_id = {str(loc.id): loc for loc in locations}
    
    # Get all snapshots
    snapshots_result = await db.execute(
        select(GSVImage).where(
            GSVImage.location_id.in_(location_ids),
            GSVImage.is_user_snapshot == True
        ).order_by(GSVImage.created_at.desc())
    )
    snapshots = snapshots_result.scalars().all()
    
    return {
        "task_id": str(task_id),
        "task_name": task.name or task.group_value or task.council,
        "total_snapshots": len(snapshots),
        "snapshots": [
            {
                "id": str(s.id),
                "location_id": str(s.location_id),
                "location_identifier": locations_by_id.get(str(s.location_id), {}).identifier if str(s.location_id) in locations_by_id else "Unknown",
                "gcs_url": s.gcs_url.replace("http://localhost:8000", "") if s.gcs_url and s.gcs_url.startswith("http://localhost:8000") else s.gcs_url,
                "heading": s.heading,
                "capture_date": s.capture_date.isoformat() if s.capture_date else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ]
    }


# Pydantic model for bulk export request
from pydantic import BaseModel
from typing import List

class BulkExportRequest(BaseModel):
    task_ids: List[str]


@router.post("/bulk/csv")
async def bulk_export_csv(
    request: BulkExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Bulk export labelling results as CSV files for multiple tasks.
    Returns a ZIP file containing one CSV per task.
    """
    import os
    import logging
    logger = logging.getLogger(__name__)
    
    if not request.task_ids:
        raise HTTPException(status_code=400, detail="No task IDs provided")
    
    logger.info(f"Bulk CSV export requested for {len(request.task_ids)} tasks")
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    files_added = 0
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for task_id in request.task_ids:
            try:
                task_uuid = uuid.UUID(task_id)
            except ValueError:
                logger.warning(f"Invalid task UUID: {task_id}")
                continue
            
            # Get task
            task_result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task = task_result.scalar_one_or_none()
            
            if not task:
                logger.warning(f"Task not found: {task_id}")
                continue
            
            logger.info(f"Processing task: {task.name or task.group_value or task.council}, group_field={task.group_field}, group_value={task.group_value}")
            
            # Get location type
            type_result = await db.execute(
                select(LocationType).where(LocationType.id == task.location_type_id)
            )
            location_type = type_result.scalar_one_or_none()
            
            # Build query for this task's locations - use same logic as single task export
            from sqlalchemy import text
            
            base_query = select(Location).where(Location.location_type_id == task.location_type_id)
            
            # Apply group filter using same logic as export_task_csv
            if task.group_field and task.group_field.startswith("original_"):
                original_key = task.group_field.replace("original_", "")
                base_query = base_query.where(
                    text(f"original_data->>'{original_key}' = :group_value")
                ).params(group_value=task.group_value)
                logger.info(f"Filtering by original_data->>'{original_key}' = {task.group_value}")
            elif task.group_field == "council" or not task.group_field:
                filter_value = task.group_value or task.council
                if filter_value:
                    base_query = base_query.where(Location.council == filter_value)
                    logger.info(f"Filtering by council = {filter_value}")
            elif task.group_field == "combined_authority":
                base_query = base_query.where(Location.combined_authority == task.group_value)
                logger.info(f"Filtering by combined_authority = {task.group_value}")
            elif task.group_field == "road_classification":
                base_query = base_query.where(Location.road_classification == task.group_value)
                logger.info(f"Filtering by road_classification = {task.group_value}")
            elif task.group_field and task.group_value:
                # Fallback: try to match against original_data
                base_query = base_query.where(
                    text(f"original_data->>'{task.group_field}' = :group_value")
                ).params(group_value=task.group_value)
                logger.info(f"Filtering by original_data->>'{task.group_field}' = {task.group_value}")
            
            locations_result = await db.execute(base_query.order_by(Location.identifier))
            locations = locations_result.scalars().all()
            
            logger.info(f"Found {len(locations)} locations for task {task_id}")
            
            if not locations:
                logger.warning(f"No locations found for task {task_id}")
                continue
            
            location_ids = [loc.id for loc in locations]
            
            # Get labels BY TASK_ID (same as single task export) - this is the key fix!
            labels_result = await db.execute(
                select(Label).where(Label.task_id == task_uuid)
            )
            labels = {str(l.location_id): l for l in labels_result.scalars().all()}
            logger.info(f"Found {len(labels)} labels for task {task_id}")
            
            # Get images
            images_result = await db.execute(
                select(GSVImage).where(
                    GSVImage.location_id.in_(location_ids),
                    GSVImage.is_user_snapshot == False
                )
            )
            images = {}
            for img in images_result.scalars().all():
                loc_id = str(img.location_id)
                if loc_id not in images:
                    images[loc_id] = {}
                images[loc_id][img.heading] = img
            
            # Build rows
            rows = []
            for loc in locations:
                loc_id = str(loc.id)
                label = labels.get(loc_id)
                loc_images = images.get(loc_id, {})
                
                row = {
                    "identifier": loc.identifier,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "council": loc.council,
                    "combined_authority": loc.combined_authority,
                    "road_classification": loc.road_classification,
                }
                
                # Add original data fields
                if loc.original_data:
                    for key, value in loc.original_data.items():
                        if key not in row:
                            row[f"original_{key}"] = value
                
                # Add label fields
                if label:
                    row["labelled"] = True
                    row["labelled_at"] = label.created_at.isoformat() if label.created_at else None
                    if label.custom_fields:
                        for key, value in label.custom_fields.items():
                            row[f"label_{key}"] = value
                    row["label_notes"] = label.notes
                else:
                    row["labelled"] = False
                
                # Add image URLs
                for heading in [0, 90, 180, 270]:
                    img = loc_images.get(heading)
                    if img and img.gcs_url:
                        row[f"image_{heading}_url"] = img.gcs_url
                    else:
                        row[f"image_{heading}_url"] = None
                
                rows.append(row)
            
            # Create DataFrame and CSV
            logger.info(f"Built {len(rows)} rows for task {task_id}")
            
            if rows:
                df = pd.DataFrame(rows)
                csv_content = df.to_csv(index=False)
                
                # Create filename
                task_name = task.name or task.group_value or task.council or str(task.id)[:8]
                safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in task_name)
                filename = f"{safe_name}_labels.csv"
                
                zip_file.writestr(filename, csv_content)
                files_added += 1
                logger.info(f"Added {filename} to ZIP ({len(csv_content)} bytes)")
    
    logger.info(f"Total files added to ZIP: {files_added}")
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=labelling_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        }
    )


@router.post("/bulk/all")
async def bulk_export_all(
    request: BulkExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Bulk export everything for multiple tasks: CSV labels, images, and snapshots.
    Returns a ZIP file with organized folders per task.
    """
    import os
    import httpx
    from app.core.config import get_settings
    
    settings = get_settings()
    
    if not request.task_ids:
        raise HTTPException(status_code=400, detail="No task IDs provided")
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for task_id in request.task_ids:
            try:
                task_uuid = uuid.UUID(task_id)
            except ValueError:
                continue
            
            # Get task
            task_result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task = task_result.scalar_one_or_none()
            
            if not task:
                continue
            
            # Get location type
            type_result = await db.execute(
                select(LocationType).where(LocationType.id == task.location_type_id)
            )
            location_type = type_result.scalar_one_or_none()
            
            # Create folder name for this task
            task_name = task.name or task.group_value or task.council or str(task.id)[:8]
            safe_task_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in task_name)
            
            # Build query for this task's locations - use same logic as single task export
            from sqlalchemy import text
            
            base_query = select(Location).where(Location.location_type_id == task.location_type_id)
            
            # Apply group filter using same logic as export_task_csv
            if task.group_field and task.group_field.startswith("original_"):
                original_key = task.group_field.replace("original_", "")
                base_query = base_query.where(
                    text(f"original_data->>'{original_key}' = :group_value")
                ).params(group_value=task.group_value)
            elif task.group_field == "council" or not task.group_field:
                filter_value = task.group_value or task.council
                if filter_value:
                    base_query = base_query.where(Location.council == filter_value)
            elif task.group_field == "combined_authority":
                base_query = base_query.where(Location.combined_authority == task.group_value)
            elif task.group_field == "road_classification":
                base_query = base_query.where(Location.road_classification == task.group_value)
            elif task.group_field and task.group_value:
                # Fallback: try to match against original_data
                base_query = base_query.where(
                    text(f"original_data->>'{task.group_field}' = :group_value")
                ).params(group_value=task.group_value)
            
            locations_result = await db.execute(base_query.order_by(Location.identifier))
            locations = locations_result.scalars().all()
            
            if not locations:
                continue
            
            location_ids = [loc.id for loc in locations]
            locations_by_id = {str(loc.id): loc for loc in locations}
            
            # Get labels BY TASK_ID (same as single task export) - this is the key fix!
            labels_result = await db.execute(
                select(Label).where(Label.task_id == task_uuid)
            )
            labels = {str(l.location_id): l for l in labels_result.scalars().all()}
            
            # Get ALL images (including snapshots)
            images_result = await db.execute(
                select(GSVImage).where(GSVImage.location_id.in_(location_ids))
            )
            all_images = images_result.scalars().all()
            
            # Organize images
            images_by_location = {}
            snapshots = []
            for img in all_images:
                loc_id = str(img.location_id)
                if img.is_user_snapshot:
                    snapshots.append(img)
                else:
                    if loc_id not in images_by_location:
                        images_by_location[loc_id] = {}
                    images_by_location[loc_id][img.heading] = img
            
            # Build CSV rows
            rows = []
            for loc in locations:
                loc_id = str(loc.id)
                label = labels.get(loc_id)
                loc_images = images_by_location.get(loc_id, {})
                
                row = {
                    "identifier": loc.identifier,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "council": loc.council,
                    "combined_authority": loc.combined_authority,
                    "road_classification": loc.road_classification,
                }
                
                if loc.original_data:
                    for key, value in loc.original_data.items():
                        if key not in row:
                            row[f"original_{key}"] = value
                
                if label:
                    row["labelled"] = True
                    row["labelled_at"] = label.created_at.isoformat() if label.created_at else None
                    if label.custom_fields:
                        for key, value in label.custom_fields.items():
                            row[f"label_{key}"] = value
                    row["label_notes"] = label.notes
                else:
                    row["labelled"] = False
                
                for heading in [0, 90, 180, 270]:
                    img = loc_images.get(heading)
                    if img and img.gcs_url:
                        row[f"image_{heading}_url"] = img.gcs_url
                    else:
                        row[f"image_{heading}_url"] = None
                
                rows.append(row)
            
            # Add CSV to ZIP
            if rows:
                df = pd.DataFrame(rows)
                csv_content = df.to_csv(index=False)
                zip_file.writestr(f"{safe_task_name}/labels.csv", csv_content)
            
            # Add images to ZIP
            async def fetch_image(url: str) -> bytes | None:
                """Fetch image from URL or local path."""
                try:
                    if url.startswith('/api/v1/images/'):
                        # Local file
                        local_path = url.replace('/api/v1/images/', '')
                        full_path = os.path.join(settings.LOCAL_STORAGE_PATH or '/app/local_storage', local_path)
                        if os.path.exists(full_path):
                            with open(full_path, 'rb') as f:
                                return f.read()
                    elif url.startswith('http'):
                        async with httpx.AsyncClient() as client:
                            response = await client.get(url, timeout=30.0)
                            if response.status_code == 200:
                                return response.content
                    return None
                except Exception:
                    return None
            
            # Add street view images for labelled locations
            labelled_location_ids = set(labels.keys())
            for loc_id, loc_images_dict in images_by_location.items():
                if loc_id not in labelled_location_ids:
                    continue  # Only include images for labelled locations
                
                loc = locations_by_id.get(loc_id)
                if not loc:
                    continue
                
                safe_identifier = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in (loc.identifier or loc_id[:8]))
                
                for heading, img in loc_images_dict.items():
                    if img.gcs_url:
                        img_data = await fetch_image(img.gcs_url)
                        if img_data:
                            zip_file.writestr(
                                f"{safe_task_name}/images/{safe_identifier}_{heading}.jpg",
                                img_data
                            )
            
            # Add snapshots
            for snapshot in snapshots:
                if snapshot.gcs_url:
                    loc = locations_by_id.get(str(snapshot.location_id))
                    safe_identifier = "".join(
                        c if c.isalnum() or c in ('-', '_') else '_' 
                        for c in (loc.identifier if loc else str(snapshot.location_id)[:8])
                    )
                    
                    img_data = await fetch_image(snapshot.gcs_url)
                    if img_data:
                        timestamp = snapshot.created_at.strftime('%Y%m%d_%H%M%S') if snapshot.created_at else 'unknown'
                        zip_file.writestr(
                            f"{safe_task_name}/snapshots/{safe_identifier}_{timestamp}.jpg",
                            img_data
                        )
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=labelling_complete_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        }
    )

