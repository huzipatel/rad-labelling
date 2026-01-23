"""Celery background tasks."""
import asyncio
from celery import Celery
from uuid import UUID

from app.core.config import settings


# Create Celery app
celery_app = Celery(
    "labelling_tasks",
    broker=settings.celery_broker,
    backend=settings.celery_backend
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=43200,  # 12 hours max per task (for large downloads)
    task_soft_time_limit=42000,  # 11.5 hours soft limit (allows graceful shutdown)
    worker_prefetch_multiplier=1,  # Only fetch one task at a time per worker
    task_acks_late=True,  # Acknowledge tasks after completion (safer for long tasks)
)


def run_async(coro):
    """Helper to run async functions in Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="download_task_images", max_retries=3)
def download_task_images_celery(self, task_id: str, download_log_id: str = None):
    """
    Download Google Street View images for all locations in a task.
    
    This is a long-running task that updates progress as it goes.
    Handles download logs, progress tracking, and error recovery.
    """
    from app.core.database import get_celery_session_maker
    from app.models.task import Task
    from app.models.location import Location
    from app.models.gsv_image import GSVImage
    from app.models.download_log import DownloadLog
    from app.services.gsv_downloader import GSVDownloader
    from sqlalchemy import select, and_
    from sqlalchemy.orm import selectinload
    from datetime import datetime
    import traceback
    
    async def _download():
        print(f"[Celery GSV Download] Starting download for task {task_id}")
        
        # Check GSV API keys - either single key or comma-separated list
        has_keys = settings.GSV_API_KEY or settings.GSV_API_KEYS
        if not has_keys:
            print(f"[Celery GSV Download] ERROR: No GSV API keys configured!")
            return {"error": "GSV_API_KEY or GSV_API_KEYS must be set in environment variables."}
        
        if settings.GSV_API_KEY:
            print(f"[Celery GSV Download] GSV_API_KEY configured: {settings.GSV_API_KEY[:8]}...")
        if settings.GSV_API_KEYS:
            key_count = len([k for k in settings.GSV_API_KEYS.split(",") if k.strip()])
            print(f"[Celery GSV Download] GSV_API_KEYS configured with {key_count} keys")
        
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Get task with location type
            result = await db.execute(
                select(Task).options(selectinload(Task.location_type)).where(Task.id == UUID(task_id))
            )
            task = result.scalar_one_or_none()
            
            if not task:
                return {"error": "Task not found"}
            
            # Get or create download log
            download_log = None
            if download_log_id:
                log_result = await db.execute(
                    select(DownloadLog).where(DownloadLog.id == UUID(download_log_id))
                )
                download_log = log_result.scalar_one_or_none()
            
            if not download_log:
                download_log = DownloadLog(
                    task_id=task.id,
                    status="running",
                    started_at=datetime.utcnow()
                )
                db.add(download_log)
                await db.commit()
                await db.refresh(download_log)
            else:
                download_log.status = "running"
                download_log.started_at = datetime.utcnow()
                await db.commit()
            
            # Update task status
            task.status = "downloading"
            await db.commit()
            
            try:
                # Get location type info
                location_type_name = task.location_type.name if task.location_type else "unknown"
                
                # Build location query based on task grouping
                # Start with base query filtering by location type
                from sqlalchemy import text
                
                base_query = select(Location).where(Location.location_type_id == task.location_type_id)
                
                # Handle different group field types
                if task.group_field and task.group_field.startswith("original_"):
                    # Group field is from original spreadsheet data (JSONB)
                    original_key = task.group_field.replace("original_", "")
                    location_query = base_query.where(
                        text(f"original_data->>'{original_key}' = :group_value")
                    ).params(group_value=task.group_value)
                    print(f"[Celery GSV Download] Using original field '{original_key}' = '{task.group_value}'")
                elif task.group_field == "council":
                    location_query = base_query.where(Location.council == task.group_value)
                    print(f"[Celery GSV Download] Using council = '{task.group_value}'")
                elif task.group_field == "combined_authority":
                    location_query = base_query.where(Location.combined_authority == task.group_value)
                    print(f"[Celery GSV Download] Using combined_authority = '{task.group_value}'")
                elif task.group_field == "road_classification":
                    location_query = base_query.where(Location.road_classification == task.group_value)
                    print(f"[Celery GSV Download] Using road_classification = '{task.group_value}'")
                elif task.council:
                    # Fallback to council field if no group_field set
                    location_query = base_query.where(Location.council == task.council)
                    print(f"[Celery GSV Download] Using council (fallback) = '{task.council}'")
                else:
                    # No grouping - get all locations for this location type
                    location_query = base_query
                    print(f"[Celery GSV Download] No group filter - getting all locations for location_type_id={task.location_type_id}")
                
                locations_result = await db.execute(location_query)
                locations = locations_result.scalars().all()
                
                total_locations = len(locations)
                download_log.total_locations = total_locations
                await db.commit()
                
                print(f"[Celery GSV Download] Found {total_locations} locations to process")
                print(f"[Celery GSV Download] Task info: group_field='{task.group_field}', group_value='{task.group_value}', council='{task.council}'")
                
                if total_locations == 0:
                    # No locations found - this might indicate a query issue
                    error_msg = f"No locations found for task. group_field='{task.group_field}', group_value='{task.group_value}'"
                    print(f"[Celery GSV Download] WARNING: {error_msg}")
                    download_log.status = "completed"
                    download_log.completed_at = datetime.utcnow()
                    download_log.last_error = error_msg
                    task.status = "ready"  # Mark as ready even with 0 images
                    await db.commit()
                    return {"task_id": task_id, "images_downloaded": 0, "error": error_msg}
                
                # Initialize downloader
                downloader = GSVDownloader()
                
                # Count EXISTING images in database first (for accurate totals)
                from sqlalchemy import func
                location_ids = [loc.id for loc in locations]
                existing_count_result = await db.execute(
                    select(func.count(GSVImage.id)).where(GSVImage.location_id.in_(location_ids))
                )
                existing_images_count = existing_count_result.scalar() or 0
                
                # Start with existing count so we don't lose progress
                images_downloaded = existing_images_count
                new_downloads = 0
                failed_downloads = 0
                skipped_existing = 0
                processed = 0
                
                # Update task with accurate current count immediately
                task.images_downloaded = images_downloaded
                await db.commit()
                print(f"[Celery GSV Download] Starting with {existing_images_count} existing images")
                
                for location in locations:
                    processed += 1
                    download_log.processed_locations = processed
                    download_log.current_location_id = location.id
                    download_log.current_location_identifier = location.identifier
                    
                    # Check if images already exist for this location
                    existing_result = await db.execute(
                        select(GSVImage).where(GSVImage.location_id == location.id)
                    )
                    existing_images = existing_result.scalars().all()
                    
                    if existing_images:
                        skipped_existing += len(existing_images)
                        download_log.skipped_existing = skipped_existing
                        # Don't continue - we already counted these in images_downloaded
                        continue
                    
                    try:
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
                        new_downloads += downloaded
                        download_log.successful_downloads = new_downloads
                        
                    except Exception as e:
                        print(f"[Celery GSV Download] Error for {location.identifier}: {e}")
                        failed_downloads += 1
                        download_log.failed_downloads = failed_downloads
                        download_log.last_error = str(e)
                        download_log.error_count += 1
                    
                    # Update progress
                    task.images_downloaded = images_downloaded
                    await db.commit()
                    
                    # Update Celery task state
                    percent = int((processed / total_locations) * 100) if total_locations > 0 else 0
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "current": processed,
                            "total": total_locations,
                            "images_downloaded": images_downloaded,
                            "percent": percent
                        }
                    )
                    
                    # Log progress every 10 locations
                    if processed % 10 == 0:
                        print(f"[Celery GSV Download] Progress: {processed}/{total_locations}, {images_downloaded} images")
                
                # Mark task as ready
                task.images_downloaded = images_downloaded
                if task.status == "downloading":
                    task.status = "ready"
                
                download_log.status = "completed"
                download_log.completed_at = datetime.utcnow()
                download_log.current_location_id = None
                download_log.current_location_identifier = None
                
                await db.commit()
                
                print(f"[Celery GSV Download] Complete! Total: {images_downloaded} images ({new_downloads} new, {skipped_existing} previously existed), {failed_downloads} failed")
                
                return {
                    "task_id": task_id,
                    "images_downloaded": images_downloaded,
                    "new_downloads": new_downloads,
                    "skipped_existing": skipped_existing,
                    "failed_downloads": failed_downloads,
                    "total_locations": total_locations
                }
                
            except Exception as e:
                error_msg = f"Fatal error: {str(e)}\n{traceback.format_exc()}"
                print(f"[Celery GSV Download] [ERROR] {error_msg}")
                
                download_log.status = "failed"
                download_log.last_error = str(e)
                task.status = "failed"
                await db.commit()
                
                return {"error": str(e)}
    
    return run_async(_download())


@celery_app.task(bind=True, name="download_all_tasks_sequential", max_retries=1)
def download_all_tasks_sequential(self, task_ids: list):
    """
    Download images for multiple tasks SEQUENTIALLY (one at a time).
    
    This ensures tasks are processed in order and prevents overwhelming
    the GSV API or worker resources.
    """
    from app.core.database import get_celery_session_maker
    from app.models.task import Task
    from app.models.location import Location
    from app.models.gsv_image import GSVImage
    from app.models.download_log import DownloadLog
    from app.services.gsv_downloader import GSVDownloader
    from sqlalchemy import select, and_, text
    from sqlalchemy.orm import selectinload
    from datetime import datetime
    import traceback
    
    async def _download_all():
        print(f"[Celery Sequential] Starting sequential download for {len(task_ids)} tasks")
        
        # Check GSV API key first
        if not settings.GSV_API_KEY:
            print(f"[Celery Sequential] ERROR: GSV_API_KEY is not configured!")
            return {"error": "GSV_API_KEY is not configured"}
        
        print(f"[Celery Sequential] GSV_API_KEY configured: {settings.GSV_API_KEY[:8]}...")
        
        session_maker = get_celery_session_maker()
        results = []
        
        for task_index, task_id in enumerate(task_ids):
            print(f"\n[Celery Sequential] === Processing task {task_index + 1}/{len(task_ids)}: {task_id} ===")
            
            # Update Celery state
            self.update_state(
                state="PROGRESS",
                meta={
                    "current_task": task_index + 1,
                    "total_tasks": len(task_ids),
                    "current_task_id": task_id,
                    "percent": int((task_index / len(task_ids)) * 100)
                }
            )
            
            async with session_maker() as db:
                try:
                    # Get task with location type
                    result = await db.execute(
                        select(Task).options(selectinload(Task.location_type)).where(Task.id == UUID(task_id))
                    )
                    task = result.scalar_one_or_none()
                    
                    if not task:
                        print(f"[Celery Sequential] Task {task_id} not found, skipping")
                        results.append({"task_id": task_id, "error": "Task not found"})
                        continue
                    
                    # Create download log
                    download_log = DownloadLog(
                        task_id=task.id,
                        status="in_progress",
                        started_at=datetime.utcnow(),
                        total_locations=task.total_locations
                    )
                    db.add(download_log)
                    
                    # Update task status
                    task.status = "downloading"
                    await db.commit()
                    await db.refresh(download_log)
                    
                    # Get location type info
                    location_type_name = task.location_type.name if task.location_type else "unknown"
                    
                    # Build location query based on task grouping
                    base_query = select(Location).where(Location.location_type_id == task.location_type_id)
                    
                    # Handle different group field types
                    if task.group_field and task.group_field.startswith("original_"):
                        original_key = task.group_field.replace("original_", "")
                        location_query = base_query.where(
                            text(f"original_data->>'{original_key}' = :group_value")
                        ).params(group_value=task.group_value)
                        print(f"[Celery Sequential] Using original field '{original_key}' = '{task.group_value}'")
                    elif task.group_field == "council":
                        location_query = base_query.where(Location.council == task.group_value)
                    elif task.group_field == "combined_authority":
                        location_query = base_query.where(Location.combined_authority == task.group_value)
                    elif task.group_field == "road_classification":
                        location_query = base_query.where(Location.road_classification == task.group_value)
                    elif task.council:
                        location_query = base_query.where(Location.council == task.council)
                    else:
                        location_query = base_query
                    
                    locations_result = await db.execute(location_query)
                    locations = locations_result.scalars().all()
                    
                    total_locations = len(locations)
                    download_log.total_locations = total_locations
                    await db.commit()
                    
                    print(f"[Celery Sequential] Found {total_locations} locations for task {task.name or task.group_value}")
                    
                    if total_locations == 0:
                        download_log.status = "completed"
                        download_log.completed_at = datetime.utcnow()
                        download_log.last_error = "No locations found"
                        task.status = "ready"
                        await db.commit()
                        results.append({"task_id": task_id, "images_downloaded": 0, "error": "No locations found"})
                        continue
                    
                    # Initialize downloader
                    downloader = GSVDownloader()
                    
                    images_downloaded = 0
                    failed_downloads = 0
                    skipped_existing = 0
                    processed = 0
                    
                    for location in locations:
                        processed += 1
                        download_log.processed_locations = processed
                        download_log.current_location_id = location.id
                        download_log.current_location_identifier = location.identifier
                        
                        # Check if images already exist
                        existing_result = await db.execute(
                            select(GSVImage).where(GSVImage.location_id == location.id)
                        )
                        existing_images = existing_result.scalars().all()
                        
                        if existing_images:
                            skipped_existing += len(existing_images)
                            download_log.skipped_existing = skipped_existing
                            continue
                        
                        try:
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
                            download_log.successful_downloads += downloaded
                            
                        except Exception as e:
                            print(f"[Celery Sequential] Error for {location.identifier}: {e}")
                            failed_downloads += 1
                            download_log.failed_downloads = failed_downloads
                            download_log.last_error = str(e)
                            download_log.error_count += 1
                        
                        # Update progress
                        task.images_downloaded = images_downloaded
                        await db.commit()
                        
                        # Log progress every 10 locations
                        if processed % 10 == 0:
                            print(f"[Celery Sequential] Task {task_index + 1}: {processed}/{total_locations} locations, {images_downloaded} images")
                    
                    # Mark task as ready
                    task.images_downloaded = images_downloaded
                    task.status = "ready"
                    
                    download_log.status = "completed"
                    download_log.completed_at = datetime.utcnow()
                    download_log.current_location_id = None
                    download_log.current_location_identifier = None
                    
                    await db.commit()
                    
                    print(f"[Celery Sequential] Task {task_index + 1} complete: {images_downloaded} images, {skipped_existing} skipped, {failed_downloads} failed")
                    
                    results.append({
                        "task_id": task_id,
                        "task_name": task.name or task.group_value,
                        "images_downloaded": images_downloaded,
                        "skipped_existing": skipped_existing,
                        "failed_downloads": failed_downloads,
                        "total_locations": total_locations
                    })
                    
                except Exception as e:
                    error_msg = f"Error processing task {task_id}: {str(e)}"
                    print(f"[Celery Sequential] {error_msg}\n{traceback.format_exc()}")
                    results.append({"task_id": task_id, "error": str(e)})
        
        print(f"\n[Celery Sequential] === All {len(task_ids)} tasks completed ===")
        return {"completed": len(results), "results": results}
    
    return run_async(_download_all())


@celery_app.task(bind=True, name="enhance_locations", max_retries=3)
def enhance_locations(self, location_type_id: str):
    """
    Enhance all locations of a type with spatial data.
    """
    from app.core.database import get_celery_session_maker
    from app.models.location import Location
    from app.services.spatial_enhancer import SpatialEnhancer
    from sqlalchemy import select
    
    async def _enhance():
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Get unenhanced locations
            result = await db.execute(
                select(Location).where(
                    Location.location_type_id == UUID(location_type_id),
                    Location.is_enhanced == False
                )
            )
            locations = result.scalars().all()
            
            if not locations:
                return {"enhanced": 0, "message": "No locations to enhance"}
            
            enhancer = SpatialEnhancer(db)
            enhanced = 0
            total = len(locations)
            
            for loc in locations:
                try:
                    data = await enhancer.enhance_location(
                        loc.latitude,
                        loc.longitude
                    )
                    
                    loc.council = data.get("council")
                    loc.road_classification = data.get("road_classification")
                    loc.combined_authority = data.get("combined_authority")
                    loc.is_enhanced = True
                    
                    enhanced += 1
                    
                    # Update progress
                    if enhanced % 100 == 0:
                        await db.commit()
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "current": enhanced,
                                "total": total,
                                "percent": int((enhanced / total) * 100)
                            }
                        )
                    
                except Exception as e:
                    print(f"Error enhancing location {loc.id}: {e}")
            
            await db.commit()
            
            return {
                "enhanced": enhanced,
                "total": total
            }
    
    return run_async(_enhance())


@celery_app.task(bind=True, name="process_spreadsheet_upload", max_retries=3)
def process_spreadsheet_upload(self, job_id: str):
    """
    Process a spreadsheet upload in the background.
    
    This handles large CSV/Excel files with hundreds of thousands of rows.
    Uses chunked reading for memory efficiency and speed.
    """
    from app.core.database import get_celery_session_maker
    from app.models.shapefile import UploadJob
    from app.models.location import Location, LocationType
    from sqlalchemy import select
    from datetime import datetime
    import os
    import pandas as pd
    
    print(f"[Celery] Task started for job {job_id}")
    
    async def _process():
        # Create a fresh session maker for this task
        session_maker = get_celery_session_maker()
        
        async with session_maker() as db:
            # Get the upload job
            result = await db.execute(
                select(UploadJob).where(UploadJob.id == UUID(job_id))
            )
            job = result.scalar_one_or_none()
            
            if not job:
                return {"error": "Upload job not found"}
            
            try:
                # Update status
                job.status = "processing"
                job.stage = "Starting file processing"
                job.progress_percent = 1
                await db.commit()
                
                print(f"[Celery] Starting spreadsheet processing for job {job_id}")
                
                # Get job metadata
                metadata = job.job_metadata
                location_type_id = metadata.get("location_type_id")
                lat_column = metadata.get("lat_column", "Latitude")
                lng_column = metadata.get("lng_column", "Longitude")
                identifier_column = metadata.get("identifier_column", "ATCOCode")
                
                # Get location type
                result = await db.execute(
                    select(LocationType).where(LocationType.id == UUID(location_type_id))
                )
                location_type = result.scalar_one_or_none()
                
                if not location_type:
                    raise Exception("Location type not found")
                
                # Read and parse the file
                file_path = job.file_path
                if not file_path or not os.path.exists(file_path):
                    raise Exception(f"File not found: {file_path}")
                
                ext = file_path.split(".")[-1].lower()
                
                job.stage = "Counting rows..."
                job.progress_percent = 2
                await db.commit()
                
                # For CSV, count rows first (fast)
                if ext == "csv":
                    # Count total rows quickly
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        total_rows = sum(1 for _ in f) - 1  # Subtract header
                    
                    print(f"[Celery] CSV has {total_rows:,} rows")
                    
                    job.stage = f"Processing {total_rows:,} rows..."
                    job.progress_percent = 5
                    job.job_metadata = {**metadata, "total_rows": total_rows}
                    await db.commit()
                    
                    self.update_state(
                        state="PROGRESS",
                        meta={"stage": "Processing CSV", "percent": 5, "total": total_rows}
                    )
                    
                    # Process CSV in chunks using pandas
                    locations_created = 0
                    chunk_size = 10000  # Process 10k rows at a time
                    
                    for chunk_num, chunk_df in enumerate(pd.read_csv(file_path, chunksize=chunk_size)):
                        # Strip column names
                        chunk_df.columns = chunk_df.columns.str.strip()
                        
                        # Case-insensitive column matching
                        column_map = {col.lower(): col for col in chunk_df.columns}
                        actual_lat = column_map.get(lat_column.lower(), lat_column)
                        actual_lng = column_map.get(lng_column.lower(), lng_column)
                        actual_id = column_map.get(identifier_column.lower(), identifier_column)
                        
                        # Filter valid rows using vectorized operations (FAST)
                        valid_mask = (
                            chunk_df[actual_lat].notna() &
                            chunk_df[actual_lng].notna() &
                            chunk_df[actual_id].notna() &
                            (chunk_df[actual_lat].astype(float) >= -90) &
                            (chunk_df[actual_lat].astype(float) <= 90) &
                            (chunk_df[actual_lng].astype(float) >= -180) &
                            (chunk_df[actual_lng].astype(float) <= 180)
                        )
                        valid_df = chunk_df[valid_mask]
                        
                        # Batch insert using bulk operations
                        locations_batch = []
                        for _, row in valid_df.iterrows():
                            original_data = {}
                            for key, value in row.items():
                                if pd.isna(value):
                                    original_data[key] = None
                                elif hasattr(value, 'isoformat'):
                                    original_data[key] = value.isoformat()
                                else:
                                    original_data[key] = value
                            
                            locations_batch.append(Location(
                                location_type_id=location_type.id,
                                identifier=str(row[actual_id]).strip(),
                                latitude=float(row[actual_lat]),
                                longitude=float(row[actual_lng]),
                                original_data=original_data
                            ))
                        
                        # Bulk add all locations in this chunk
                        db.add_all(locations_batch)
                        await db.commit()
                        
                        locations_created += len(locations_batch)
                        
                        # Update progress
                        percent = 5 + int((locations_created / total_rows) * 90)
                        job.stage = f"Created {locations_created:,} of {total_rows:,} locations"
                        job.progress_percent = percent
                        await db.commit()
                        
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "stage": f"Creating locations ({locations_created:,}/{total_rows:,})",
                                "percent": percent,
                                "current": locations_created,
                                "total": total_rows
                            }
                        )
                        
                        print(f"[Celery] Processed chunk {chunk_num + 1}, {locations_created:,} locations created ({percent}%)")
                
                else:
                    # Excel files - read all at once (can't chunk easily)
                    job.stage = "Reading Excel file..."
                    job.progress_percent = 5
                    await db.commit()
                    
                    df = pd.read_excel(file_path)
                    total_rows = len(df)
                    
                    job.stage = f"Processing {total_rows:,} rows from Excel..."
                    job.progress_percent = 20
                    job.job_metadata = {**metadata, "total_rows": total_rows}
                    await db.commit()
                    
                    # Process in memory batches
                    df.columns = df.columns.str.strip()
                    column_map = {col.lower(): col for col in df.columns}
                    actual_lat = column_map.get(lat_column.lower(), lat_column)
                    actual_lng = column_map.get(lng_column.lower(), lng_column)
                    actual_id = column_map.get(identifier_column.lower(), identifier_column)
                    
                    locations_created = 0
                    batch_size = 5000
                    
                    for start_idx in range(0, total_rows, batch_size):
                        end_idx = min(start_idx + batch_size, total_rows)
                        batch_df = df.iloc[start_idx:end_idx]
                        
                        locations_batch = []
                        for _, row in batch_df.iterrows():
                            try:
                                lat = float(row[actual_lat])
                                lng = float(row[actual_lng])
                                identifier = str(row[actual_id]).strip()
                                
                                if not identifier or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                                    continue
                                
                                original_data = {}
                                for key, value in row.items():
                                    if pd.isna(value):
                                        original_data[key] = None
                                    elif hasattr(value, 'isoformat'):
                                        original_data[key] = value.isoformat()
                                    else:
                                        original_data[key] = value
                                
                                locations_batch.append(Location(
                                    location_type_id=location_type.id,
                                    identifier=identifier,
                                    latitude=lat,
                                    longitude=lng,
                                    original_data=original_data
                                ))
                            except:
                                continue
                        
                        db.add_all(locations_batch)
                        await db.commit()
                        
                        locations_created += len(locations_batch)
                        percent = 20 + int((locations_created / total_rows) * 75)
                        job.stage = f"Created {locations_created:,} of {total_rows:,} locations"
                        job.progress_percent = percent
                        await db.commit()
                        
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "stage": f"Creating locations ({locations_created:,}/{total_rows:,})",
                                "percent": percent,
                                "current": locations_created,
                                "total": total_rows
                            }
                        )
                
                # Mark as completed
                job.status = "completed"
                job.stage = f"Successfully created {locations_created:,} locations"
                job.progress_percent = 100
                job.completed_at = datetime.utcnow()
                job.job_metadata = {
                    **metadata,
                    "total_rows": total_rows,
                    "locations_created": locations_created
                }
                await db.commit()
                
                # Clean up the temp file
                try:
                    os.remove(file_path)
                except:
                    pass
                
                print(f"[Celery] Completed! Created {locations_created:,} locations")
                
                return {
                    "job_id": job_id,
                    "locations_created": locations_created,
                    "total_rows": total_rows
                }
                
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                print(f"[Celery] ERROR: {error_msg}")
                
                try:
                    job.status = "failed"
                    job.stage = "Upload failed"
                    job.error_message = str(e)[:500]  # Limit error message length
                    await db.commit()
                except:
                    pass  # If we can't update the job, just log it
                
                return {"error": str(e)}
    
    try:
        return run_async(_process())
    except Exception as e:
        import traceback
        print(f"[Celery] FATAL ERROR in task: {e}\n{traceback.format_exc()}")
        
        # Check if it's a connection error - if so, retry
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            print(f"[Celery] Retrying due to connection error...")
            raise self.retry(exc=e, countdown=30)  # Retry after 30 seconds
        
        raise


@celery_app.task(name="notify_task_completion", max_retries=3)
def notify_task_completion(task_id: str):
    """
    Send WhatsApp notification when a task is completed.
    """
    from app.core.database import get_celery_session_maker
    from app.models.task import Task
    from app.models.user import User
    from app.services.whatsapp_notifier import WhatsAppNotifier
    from sqlalchemy import select
    
    async def _notify():
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Get task
            result = await db.execute(
                select(Task).where(Task.id == UUID(task_id))
            )
            task = result.scalar_one_or_none()
            
            if not task or task.status != "completed":
                return
            
            # Get managers with WhatsApp numbers
            managers_result = await db.execute(
                select(User).where(
                    User.role.in_(["labelling_manager", "admin"]),
                    User.whatsapp_number.isnot(None)
                )
            )
            managers = managers_result.scalars().all()
            
            if not managers:
                return
            
            # Calculate duration
            duration = "Unknown"
            if task.started_at and task.completed_at:
                delta = task.completed_at - task.started_at
                hours = delta.total_seconds() / 3600
                duration = f"{hours:.1f} hours"
            
            # Calculate rate
            rate = "N/A"
            if task.started_at and task.completed_at and task.completed_locations > 0:
                hours = (task.completed_at - task.started_at).total_seconds() / 3600
                if hours > 0:
                    rate = f"{task.completed_locations / hours:.1f}"
            
            notifier = WhatsAppNotifier()
            
            task_info = {
                "location_type": task.location_type.display_name,
                "council": task.council,
                "labeller_name": task.assignee.name if task.assignee else "Unknown",
                "completed": task.completed_locations,
                "total": task.total_locations,
                "with_advertising": 0,  # Would need to query labels
                "unable": task.failed_locations,
                "duration": duration,
                "rate": rate
            }
            
            for manager in managers:
                await notifier.notify_task_completion(
                    manager.whatsapp_number,
                    task_info
                )
    
    return run_async(_notify())

