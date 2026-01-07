"""Export service for generating CSV and ZIP files."""
import io
import zipfile
from typing import List, Optional
from datetime import datetime
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.location import Location
from app.models.label import Label
from app.models.gsv_image import GSVImage
from app.services.gcs_storage import GCSStorage


class ExportService:
    """Service for exporting labelling data."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = GCSStorage()
    
    async def export_labels_to_csv(
        self,
        location_type_id: str,
        council: Optional[str] = None,
        include_images: bool = True
    ) -> io.StringIO:
        """
        Export labels to CSV format.
        
        Args:
            location_type_id: Filter by location type
            council: Optional filter by council
            include_images: Whether to include image URLs
        
        Returns:
            StringIO containing CSV data
        """
        # Build query
        query = (
            select(Location, Label)
            .outerjoin(Label, Label.location_id == Location.id)
            .where(Location.location_type_id == location_type_id)
        )
        
        if council:
            query = query.where(Location.council == council)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Build data rows
        data = []
        for loc, label in rows:
            row = {
                "identifier": loc.identifier,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "council": loc.council,
                "combined_authority": loc.combined_authority,
                "road_classification": loc.road_classification,
            }
            
            if label:
                row.update({
                    "advertising_present": label.advertising_present,
                    "bus_shelter_present": label.bus_shelter_present,
                    "number_of_panels": label.number_of_panels,
                    "pole_stop": label.pole_stop,
                    "unmarked_stop": label.unmarked_stop,
                    "notes": label.notes,
                    "unable_to_label": label.unable_to_label,
                    "unable_reason": label.unable_reason,
                    "labelled_at": label.labelling_completed_at.isoformat() if label.labelling_completed_at else None
                })
                
                # Add custom fields
                if label.custom_fields:
                    for key, value in label.custom_fields.items():
                        row[f"custom_{key}"] = value
            
            if include_images:
                # Get images for this location
                images_result = await self.db.execute(
                    select(GSVImage).where(GSVImage.location_id == loc.id)
                )
                images = images_result.scalars().all()
                
                for img in images:
                    if img.is_user_snapshot:
                        row["snapshot_url"] = img.gcs_url
                        row["snapshot_date"] = img.capture_date.isoformat() if img.capture_date else None
                    else:
                        row[f"image_{img.heading}_url"] = img.gcs_url
                        row[f"image_{img.heading}_date"] = img.capture_date.isoformat() if img.capture_date else None
            
            data.append(row)
        
        # Create DataFrame and export
        df = pd.DataFrame(data)
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return output
    
    async def export_images_to_zip(
        self,
        location_type_id: str,
        council: Optional[str] = None,
        only_with_advertising: bool = True
    ) -> io.BytesIO:
        """
        Export images as a ZIP file.
        
        Args:
            location_type_id: Filter by location type
            council: Optional filter by council
            only_with_advertising: Only include locations with advertising
        
        Returns:
            BytesIO containing ZIP data
        """
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
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Create ZIP file
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            processed = set()
            
            for loc, label, image in rows:
                if str(image.id) in processed:
                    continue
                
                processed.add(str(image.id))
                
                try:
                    # Download image from GCS
                    image_data = await self.storage.download_file(image.gcs_path)
                    
                    # Organize by council
                    folder = loc.council.replace(" ", "_") if loc.council else "unknown"
                    
                    if image.is_user_snapshot:
                        filename = f"{folder}/{loc.identifier}_snapshot.jpg"
                    else:
                        filename = f"{folder}/{loc.identifier}_{image.heading}.jpg"
                    
                    zip_file.writestr(filename, image_data)
                    
                except Exception as e:
                    print(f"Error adding image {image.id} to ZIP: {e}")
        
        zip_buffer.seek(0)
        return zip_buffer
    
    async def generate_summary_report(
        self,
        location_type_id: str,
        council: Optional[str] = None
    ) -> dict:
        """
        Generate a summary report for labelled data.
        
        Returns dict with statistics.
        """
        # Build query
        query = (
            select(Label)
            .join(Location, Location.id == Label.location_id)
            .where(Location.location_type_id == location_type_id)
        )
        
        if council:
            query = query.where(Location.council == council)
        
        result = await self.db.execute(query)
        labels = result.scalars().all()
        
        total = len(labels)
        
        if total == 0:
            return {
                "total_locations": 0,
                "with_advertising": 0,
                "without_advertising": 0,
                "with_shelter": 0,
                "unable_to_label": 0,
                "advertising_rate": 0,
                "average_panels": 0
            }
        
        with_advertising = sum(1 for l in labels if l.advertising_present)
        with_shelter = sum(1 for l in labels if l.bus_shelter_present)
        unable = sum(1 for l in labels if l.unable_to_label)
        
        panels = [l.number_of_panels for l in labels if l.number_of_panels is not None]
        avg_panels = sum(panels) / len(panels) if panels else 0
        
        return {
            "total_locations": total,
            "with_advertising": with_advertising,
            "without_advertising": total - with_advertising - unable,
            "with_shelter": with_shelter,
            "unable_to_label": unable,
            "advertising_rate": round(with_advertising / total, 4) if total > 0 else 0,
            "average_panels": round(avg_panels, 2)
        }

