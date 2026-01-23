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
        
        # Apply rate limiting
        await gsv_key_manager.throttle()
        
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
                    print(f"[GSV] 403 on metadata, trying different key...")
                    new_key = await self._get_api_key()
                    if new_key and new_key != api_key:
                        params["key"] = new_key
                        await gsv_key_manager.throttle()
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
        
        # Apply rate limiting
        await gsv_key_manager.throttle()
        
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
                    print(f"[GSV] 403 on image download, trying different key...")
                    new_key = await self._get_api_key()
                    if new_key and new_key != api_key:
                        params["key"] = new_key
                        await gsv_key_manager.throttle()
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
                # Apply rate limiting
                await gsv_key_manager.throttle()
                
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
                        print(f"[GSV] 403 for {identifier} heading {heading}, trying different key...")
                        new_key = await self._get_api_key()
                        if new_key and new_key != api_key:
                            params["key"] = new_key
                            await gsv_key_manager.throttle()
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
        
        Args:
            db: Database session
            location_id: Location UUID
            latitude: Latitude
            longitude: Longitude
            identifier: Location identifier for filename
            location_type: Location type name for folder organization
            council: Council name for folder organization
        
        Returns:
            Number of images downloaded
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
        
        images_downloaded = 0
        for result in results:
            gsv_image = GSVImage(
                location_id=result["location_id"],
                heading=result["heading"],
                gcs_path=result["gcs_path"],
                gcs_url=result["gcs_url"],
                capture_date=result["capture_date"],
                is_user_snapshot=False
            )
            db.add(gsv_image)
            images_downloaded += 1
        
        if images_downloaded > 0:
            await db.commit()
        
        return images_downloaded

    async def download_for_task(
        self,
        task_id: UUID,
        locations: list,
        location_type: str = "unspecified",
        council: str = "unspecified",
        progress_callback=None
    ) -> dict:
        """
        Download images for all locations in a task.
        
        Args:
            task_id: Task ID
            locations: List of location dicts with id, identifier, lat, lng
            location_type: Location type name
            council: Council name
            progress_callback: Optional callback(downloaded, total)
        
        Returns:
            Summary dict with success/failure counts
        """
        total = len(locations)
        downloaded = 0
        failed = 0
        
        for loc in locations:
            try:
                results = await self.download_all_headings(
                    location_id=loc["id"],
                    identifier=loc["identifier"],
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    location_type=location_type,
                    council=loc.get("council", council)
                )
                
                if results:
                    downloaded += len(results)
                else:
                    failed += 1
                
                if progress_callback:
                    await progress_callback(downloaded, total * 4)
                
                # Rate limiting - be nice to the API
                await asyncio.sleep(0.2)
                
            except Exception as e:
                print(f"[GSV] Error downloading images for {loc['identifier']}: {e}")
                failed += 1
        
        return {
            "task_id": str(task_id),
            "total_locations": total,
            "images_downloaded": downloaded,
            "locations_failed": failed
        }
