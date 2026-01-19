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
    task_time_limit=3600,  # 1 hour max per task
)


def run_async(coro):
    """Helper to run async functions in Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="download_task_images")
def download_task_images_celery(self, task_id: str, download_log_id: str = None):
    """
    Download Google Street View images for all locations in a task.
    
    This is a long-running task that updates progress as it goes.
    Handles download logs, progress tracking, and error recovery.
    """
    from app.core.database import async_session_maker
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
        
        async with async_session_maker() as db:
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
                if task.group_field and task.group_value:
                    if task.group_field == "council":
                        location_query = select(Location).where(
                            and_(
                                Location.location_type_id == task.location_type_id,
                                Location.council == task.group_value
                            )
                        )
                    elif task.group_field == "combined_authority":
                        location_query = select(Location).where(
                            and_(
                                Location.location_type_id == task.location_type_id,
                                Location.combined_authority == task.group_value
                            )
                        )
                    else:
                        location_query = select(Location).where(
                            and_(
                                Location.location_type_id == task.location_type_id,
                                Location.council == task.council
                            )
                        )
                else:
                    location_query = select(Location).where(
                        and_(
                            Location.location_type_id == task.location_type_id,
                            Location.council == task.council
                        )
                    )
                
                locations_result = await db.execute(location_query)
                locations = locations_result.scalars().all()
                
                total_locations = len(locations)
                download_log.total_locations = total_locations
                await db.commit()
                
                print(f"[Celery GSV Download] Found {total_locations} locations to process")
                
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
                    
                    # Check if images already exist for this location
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
                
                print(f"[Celery GSV Download] Complete! {images_downloaded} images, {skipped_existing} skipped, {failed_downloads} failed")
                
                return {
                    "task_id": task_id,
                    "images_downloaded": images_downloaded,
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


@celery_app.task(bind=True, name="enhance_locations")
def enhance_locations(self, location_type_id: str):
    """
    Enhance all locations of a type with spatial data.
    """
    from app.core.database import async_session_maker
    from app.models.location import Location
    from app.services.spatial_enhancer import SpatialEnhancer
    from sqlalchemy import select
    
    async def _enhance():
        async with async_session_maker() as db:
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


@celery_app.task(bind=True, name="process_spreadsheet_upload")
def process_spreadsheet_upload(self, job_id: str):
    """
    Process a spreadsheet upload in the background.
    
    This handles large CSV/Excel files with hundreds of thousands of rows.
    """
    from app.core.database import async_session_maker
    from app.models.shapefile import UploadJob
    from app.models.location import Location, LocationType
    from app.services.spreadsheet_parser import SpreadsheetParser
    from sqlalchemy import select
    from datetime import datetime
    import os
    
    async def _process():
        async with async_session_maker() as db:
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
                job.stage = "Reading spreadsheet file"
                await db.commit()
                
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
                
                with open(file_path, "rb") as f:
                    contents = f.read()
                
                job.stage = "Parsing spreadsheet data"
                await db.commit()
                
                # Update Celery state
                self.update_state(
                    state="PROGRESS",
                    meta={"stage": "Parsing spreadsheet", "percent": 10}
                )
                
                parser = SpreadsheetParser()
                locations_data = parser.parse(
                    contents,
                    os.path.basename(file_path),
                    lat_column=lat_column,
                    lng_column=lng_column,
                    identifier_column=identifier_column
                )
                
                total_rows = len(locations_data)
                job.stage = f"Creating {total_rows:,} location records"
                job.job_metadata = {**metadata, "total_rows": total_rows}
                await db.commit()
                
                self.update_state(
                    state="PROGRESS",
                    meta={"stage": "Creating locations", "percent": 20, "total": total_rows}
                )
                
                # Create location records in batches
                locations_created = 0
                batch_size = 1000
                
                for i in range(0, total_rows, batch_size):
                    batch = locations_data[i:i + batch_size]
                    
                    for loc_data in batch:
                        location = Location(
                            location_type_id=location_type.id,
                            identifier=loc_data["identifier"],
                            latitude=loc_data["latitude"],
                            longitude=loc_data["longitude"],
                            original_data=loc_data["original_data"]
                        )
                        db.add(location)
                        locations_created += 1
                    
                    # Commit batch
                    await db.commit()
                    
                    # Update progress
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
                
                return {
                    "job_id": job_id,
                    "locations_created": locations_created,
                    "total_rows": total_rows
                }
                
            except Exception as e:
                job.status = "failed"
                job.stage = "Upload failed"
                job.error_message = str(e)
                await db.commit()
                
                return {"error": str(e)}
    
    return run_async(_process())


@celery_app.task(name="notify_task_completion")
def notify_task_completion(task_id: str):
    """
    Send WhatsApp notification when a task is completed.
    """
    from app.core.database import async_session_maker
    from app.models.task import Task
    from app.models.user import User
    from app.services.whatsapp_notifier import WhatsAppNotifier
    from sqlalchemy import select
    
    async def _notify():
        async with async_session_maker() as db:
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

