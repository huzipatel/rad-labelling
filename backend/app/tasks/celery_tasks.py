"""Celery background tasks."""
import asyncio
from celery import Celery
from uuid import UUID

from app.core.config import settings


# Create Celery app
celery_app = Celery(
    "labelling_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
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
def download_task_images(self, task_id: str):
    """
    Download Google Street View images for all locations in a task.
    
    This is a long-running task that updates progress as it goes.
    """
    from app.core.database import async_session_maker
    from app.models.task import Task
    from app.models.location import Location
    from app.models.gsv_image import GSVImage
    from app.services.gsv_downloader import GSVDownloader
    from sqlalchemy import select
    
    async def _download():
        async with async_session_maker() as db:
            # Get task
            result = await db.execute(
                select(Task).where(Task.id == UUID(task_id))
            )
            task = result.scalar_one_or_none()
            
            if not task:
                return {"error": "Task not found"}
            
            # Get locations for this task
            locations_result = await db.execute(
                select(Location).where(
                    Location.location_type_id == task.location_type_id,
                    Location.council == task.council
                )
            )
            locations = locations_result.scalars().all()
            
            # Download images
            downloader = GSVDownloader()
            total = len(locations) * 4  # 4 images per location
            downloaded = 0
            
            for loc in locations:
                try:
                    images = await downloader.download_all_headings(
                        loc.id,
                        loc.identifier,
                        loc.latitude,
                        loc.longitude
                    )
                    
                    # Save image records
                    for img_data in images:
                        gsv_image = GSVImage(
                            location_id=img_data["location_id"],
                            heading=img_data["heading"],
                            gcs_path=img_data["gcs_path"],
                            gcs_url=img_data["gcs_url"],
                            capture_date=img_data["capture_date"],
                            pano_id=img_data["pano_id"]
                        )
                        db.add(gsv_image)
                        downloaded += 1
                    
                    # Update task progress
                    task.images_downloaded = downloaded
                    await db.commit()
                    
                    # Update Celery task state
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "current": downloaded,
                            "total": total,
                            "percent": int((downloaded / total) * 100)
                        }
                    )
                    
                except Exception as e:
                    print(f"Error downloading images for {loc.identifier}: {e}")
            
            # Mark task as ready
            task.status = "ready"
            await db.commit()
            
            return {
                "task_id": task_id,
                "images_downloaded": downloaded,
                "total": total
            }
    
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

