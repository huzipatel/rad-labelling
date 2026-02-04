"""Google Street View image download service with organized storage."""
import asyncio
from typing import Optional, Tuple
from datetime import date
from uuid import UUID
import httpx

from app.core.config import settings
from app.services.gcs_storage import GCSStorage
from app.services.gsv_key_manager import gsv_key_manager


# Standard headings for 360-degree coverage
HEADINGS = [0, 90, 180, 270]


class GSVDownloader:
    """Download images from Google Street View API and store in organized folders.
    
    Uses the GSV Key Manager for automatic key rotation and failover.
    """
    
    def __init__(self):
        self.base_url = "https://maps.googleapis.com/maps/api/streetview"
        self.metadata_url = f"{self.base_url}/metadata"
        self.storage = GCSStorage()
    
    async def _get_api_key(self) -> Optional[str]:
        """Get an available API key from the key manager."""
        key = await gsv_key_manager.get_key()
        if not key:
            print("[GSV] ERROR: No API keys available!")
        return key
    
    async def get_metadata(
        self,
        latitude: float,
        longitude: float
    ) -> Optional[dict]:
        """
        Get Street View metadata for a location.
        
        Returns pano_id and capture date if available.
        Uses key rotation and automatic failover.
        """
        api_key = await self._get_api_key()
        if not api_key:
            return None
        
        params = {
            "location": f"{latitude},{longitude}",
            "key": api_key
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.metadata_url, params=params)
                
                # Record the request result
                await gsv_key_manager.record_request(
                    api_key, 
                    success=response.status_code == 200,
                    status_code=response.status_code
                )
                
                if response.status_code == 403:
                    # Try with a different key
                    new_key = await self._get_api_key()
                    if new_key and new_key != api_key:
                        params["key"] = new_key
                        response = await client.get(self.metadata_url, params=params)
                        await gsv_key_manager.record_request(
                            new_key,
                            success=response.status_code == 200,
                            status_code=response.status_code
                        )
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                
                if data.get("status") != "OK":
                    return None
                
                return {
                    "pano_id": data.get("pano_id"),
                    "date": data.get("date"),  # Format: "YYYY-MM"
                    "location": data.get("location"),
                    "status": data.get("status")
                }
            except Exception as e:
                print(f"[GSV] Error getting metadata: {e}")
                return None
    
    async def download_image(
        self,
        latitude: float,
        longitude: float,
        heading: int,
        size: str = "640x480",
        pitch: int = 0
    ) -> Optional[Tuple[bytes, Optional[str]]]:
        """
        Download a single Street View image.
        
        Returns:
            Tuple of (image_bytes, capture_date) or None if unavailable
        """
        # First get metadata to check availability and get capture date
        metadata = await self.get_metadata(latitude, longitude)
        
        if not metadata:
            return None
        
        capture_date = metadata.get("date")
        
        api_key = await self._get_api_key()
        if not api_key:
            return None
        
        params = {
            "size": size,
            "location": f"{latitude},{longitude}",
            "heading": heading,
            "pitch": pitch,
            "key": api_key
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.base_url, params=params)
                
                # Record the request result
                await gsv_key_manager.record_request(
                    api_key,
                    success=response.status_code == 200,
                    status_code=response.status_code
                )
                
                if response.status_code == 403:
                    # Try with a different key
                    new_key = await self._get_api_key()
                    if new_key and new_key != api_key:
                        params["key"] = new_key
                        response = await client.get(self.base_url, params=params)
                        await gsv_key_manager.record_request(
                            new_key,
                            success=response.status_code == 200,
                            status_code=response.status_code
                        )
                
                if response.status_code != 200:
                    return None
                
                return (response.content, capture_date)
            except Exception as e:
                print(f"[GSV] Error downloading image: {e}")
                return None
    
    async def download_all_headings(
        self,
        location_id: UUID,
        identifier: str,
        latitude: float,
        longitude: float,
        location_type: str = "unspecified",
        council: str = "unspecified"
    ) -> list:
        """
        Download images for all 4 headings and upload to storage.
        
        Args:
            location_id: UUID of the location
            identifier: Location identifier (e.g., ATCO code)
            latitude: Latitude
            longitude: Longitude
            location_type: Name of location type for folder organization
            council: Council name for folder organization
        
        Returns:
            List of image metadata dicts
        """
        results = []
        
        # Get metadata first (once for all headings)
        metadata = await self.get_metadata(latitude, longitude)
        
        if not metadata:
            print(f"[GSV] No Street View available for {identifier} ({latitude}, {longitude})")
            return results
        
        capture_date_str = metadata.get("date")
        capture_date = None
        if capture_date_str:
            # Parse "YYYY-MM" format
            parts = capture_date_str.split("-")
            if len(parts) >= 2:
                capture_date = date(int(parts[0]), int(parts[1]), 1)
        
        pano_id = metadata.get("pano_id")
        
        for heading in HEADINGS:
            # Get API key for this request
            api_key = await self._get_api_key()
            if not api_key:
                print(f"[GSV] No API keys available, stopping download for {identifier}")
                break
            
            params = {
                "size": "640x480",
                "location": f"{latitude},{longitude}",
                "heading": heading,
                "pitch": 0,
                "key": api_key
            }
            
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(self.base_url, params=params)
                    
                    # Record the request
                    await gsv_key_manager.record_request(
                        api_key,
                        success=response.status_code == 200,
                        status_code=response.status_code
                    )
                    
                    # Handle 403 - try with different key
                    if response.status_code == 403:
                        new_key = await self._get_api_key()
                        if new_key and new_key != api_key:
                            params["key"] = new_key
                            response = await client.get(self.base_url, params=params)
                            await gsv_key_manager.record_request(
                                new_key,
                                success=response.status_code == 200,
                                status_code=response.status_code
                            )
                    
                    if response.status_code != 200:
                        print(f"[GSV] Failed to download {identifier} heading {heading}: HTTP {response.status_code}")
                        continue
                    
                    image_data = response.content
                    
                    # Generate filename with date
                    date_str = capture_date_str.replace("-", "") if capture_date_str else "unknown"
                    filename = f"{identifier}_{heading}_{date_str}.jpg"
                    
                    # Upload to organized storage
                    gcs_url = await self.storage.upload_image(
                        data=image_data,
                        filename=filename,
                        location_type=location_type,
                        council=council
                    )
                    
                    # Store full path for database
                    gcs_path = f"{location_type}/{council}/images/{filename}"
                    
                    results.append({
                        "location_id": location_id,
                        "heading": heading,
                        "gcs_path": gcs_path,
                        "gcs_url": gcs_url,
                        "capture_date": capture_date,
                        "pano_id": pano_id
                    })
                    
            except Exception as e:
                print(f"[GSV] Error downloading {identifier} heading {heading}: {e}")
                continue
        
        return results
    
    async def download_images_for_location(
        self,
        db,
        location_id: UUID,
        latitude: float,
        longitude: float,
        identifier: str,
        location_type: str = "unspecified",
        council: str = "unspecified"
    ) -> int:
        """
        Download images for a single location and save to database.
        
        IMPORTANT: This method downloads images to storage AND records them in the
        GSVImage database table. Both steps must succeed for the image to be usable.
        
        Args:
            db: Database session
            location_id: Location UUID
            latitude: Latitude
            longitude: Longitude
            identifier: Location identifier for filename
            location_type: Location type name for folder organization
            council: Council name for folder organization
        
        Returns:
            Number of images downloaded and saved to database
        """
        from app.models.gsv_image import GSVImage
        
        results = await self.download_all_headings(
            location_id=location_id,
            identifier=identifier,
            latitude=latitude,
            longitude=longitude,
            location_type=location_type,
            council=council
        )
        
        if not results:
            return 0
        
        images_saved = 0
        gsv_images_to_add = []
        
        for result in results:
            gsv_image = GSVImage(
                location_id=result["location_id"],
                heading=result["heading"],
                gcs_path=result["gcs_path"],
                gcs_url=result["gcs_url"],
                capture_date=result["capture_date"],
                is_user_snapshot=False
            )
            gsv_images_to_add.append(gsv_image)
        
        # Try to save all images to database
        try:
            for gsv_image in gsv_images_to_add:
                db.add(gsv_image)
            await db.commit()
            images_saved = len(gsv_images_to_add)
            print(f"[GSV] Saved {images_saved} images to database for location {identifier}")
        except Exception as e:
            # Database save failed - log the error
            # Note: Images are still in storage but not tracked in DB
            # This creates the mismatch that can cause issues elsewhere
            print(f"[GSV] ERROR: Failed to save images to database for {identifier}: {e}")
            print(f"[GSV] WARNING: {len(results)} images uploaded to storage but NOT recorded in database!")
            await db.rollback()
            # Return 0 to indicate no images were successfully processed
            # This prevents the task counter from being incremented incorrectly
            return 0
        
        return images_saved
    
    # NOTE: download_for_task is DEPRECATED - it downloads images but does NOT save
    # them to the database, causing mismatches. Use download_images_for_location instead.
    # Keeping this method commented out to prevent accidental use.
    #
    # async def download_for_task(self, task_id, locations, ...):
    #     """DEPRECATED: Does not save to database. Use download_images_for_location."""
    #     pass
