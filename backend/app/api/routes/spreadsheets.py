"""Spreadsheet upload and management routes."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.location import Location, LocationType
from app.models.task import Task
from app.api.deps import require_manager
from app.services.spreadsheet_parser import SpreadsheetParser
from app.services.spatial_enhancer import SpatialEnhancer


router = APIRouter(prefix="/spreadsheets", tags=["Spreadsheets"])


class LocationTypeCreate(BaseModel):
    """Create location type request."""
    name: str
    display_name: str
    description: Optional[str] = None
    identifier_field: str = "atco_code"
    label_fields: dict


class LocationTypeResponse(BaseModel):
    """Location type response."""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    identifier_field: str
    label_fields: dict
    location_count: int = 0
    
    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    """Spreadsheet upload response."""
    message: str
    location_type_id: str
    locations_created: int
    councils_found: List[str]


class EnhanceRequest(BaseModel):
    """Data enhancement request."""
    location_type_id: str
    enhance_council: bool = True
    enhance_road: bool = True
    enhance_authority: bool = True


class EnhanceResponse(BaseModel):
    """Data enhancement response."""
    message: str
    locations_enhanced: int
    councils_found: List[str]
    task_id: Optional[str] = None


@router.get("/location-types", response_model=List[LocationTypeResponse])
async def list_location_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List all location types."""
    result = await db.execute(select(LocationType))
    location_types = result.scalars().all()
    
    responses = []
    for lt in location_types:
        # Get location count
        count_result = await db.execute(
            select(func.count(Location.id)).where(Location.location_type_id == lt.id)
        )
        count = count_result.scalar()
        
        responses.append(LocationTypeResponse(
            id=str(lt.id),
            name=lt.name,
            display_name=lt.display_name,
            description=lt.description,
            identifier_field=lt.identifier_field,
            label_fields=lt.label_fields,
            location_count=count
        ))
    
    return responses


@router.post("/location-types", response_model=LocationTypeResponse)
async def create_location_type(
    data: LocationTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create a new location type."""
    # Check if name exists
    result = await db.execute(
        select(LocationType).where(LocationType.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location type with this name already exists"
        )
    
    location_type = LocationType(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        identifier_field=data.identifier_field,
        label_fields=data.label_fields
    )
    
    db.add(location_type)
    await db.commit()
    await db.refresh(location_type)
    
    return LocationTypeResponse(
        id=str(location_type.id),
        name=location_type.name,
        display_name=location_type.display_name,
        description=location_type.description,
        identifier_field=location_type.identifier_field,
        label_fields=location_type.label_fields,
        location_count=0
    )


@router.patch("/location-types/{type_id}/label-fields")
async def update_label_fields(
    type_id: uuid.UUID,
    label_fields: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update label fields for a location type (doesn't affect ongoing tasks)."""
    result = await db.execute(
        select(LocationType).where(LocationType.id == type_id)
    )
    location_type = result.scalar_one_or_none()
    
    if not location_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location type not found"
        )
    
    location_type.label_fields = label_fields
    await db.commit()
    
    return {"message": "Label fields updated successfully"}


@router.delete("/location-types/{type_id}")
async def delete_location_type(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete a location type and all its associated locations."""
    result = await db.execute(
        select(LocationType).where(LocationType.id == type_id)
    )
    location_type = result.scalar_one_or_none()
    
    if not location_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location type not found"
        )
    
    # Get count of locations that will be deleted
    count_result = await db.execute(
        select(func.count(Location.id)).where(Location.location_type_id == type_id)
    )
    location_count = count_result.scalar()
    
    # Delete all locations for this type (cascade should handle related records)
    await db.execute(
        Location.__table__.delete().where(Location.location_type_id == type_id)
    )
    
    # Delete the location type
    await db.delete(location_type)
    await db.commit()
    
    return {
        "message": f"Location type '{location_type.display_name}' deleted successfully",
        "locations_deleted": location_count
    }


@router.post("/upload", response_model=UploadResponse)
async def upload_spreadsheet(
    file: UploadFile = File(...),
    location_type_id: str = Form(...),
    lat_column: str = Form("Latitude"),
    lng_column: str = Form("Longitude"),
    identifier_column: str = Form("ATCOCode"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Upload a spreadsheet of locations."""
    # Validate file extension
    if file.filename:
        ext = "." + file.filename.split(".")[-1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )
    
    # Check location type exists
    result = await db.execute(
        select(LocationType).where(LocationType.id == uuid.UUID(location_type_id))
    )
    location_type = result.scalar_one_or_none()
    
    if not location_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location type not found"
        )
    
    # Parse spreadsheet
    parser = SpreadsheetParser()
    try:
        contents = await file.read()
        locations_data = parser.parse(
            contents,
            file.filename or "upload.xlsx",
            lat_column=lat_column,
            lng_column=lng_column,
            identifier_column=identifier_column
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error parsing spreadsheet: {str(e)}"
        )
    
    # Create location records
    councils_found = set()
    locations_created = 0
    
    for loc_data in locations_data:
        location = Location(
            location_type_id=location_type.id,
            identifier=loc_data["identifier"],
            latitude=loc_data["latitude"],
            longitude=loc_data["longitude"],
            original_data=loc_data["original_data"]
        )
        db.add(location)
        locations_created += 1
    
    await db.commit()
    
    return UploadResponse(
        message=f"Successfully uploaded {locations_created} locations",
        location_type_id=location_type_id,
        locations_created=locations_created,
        councils_found=list(councils_found)
    )


@router.post("/enhance", response_model=EnhanceResponse)
async def enhance_data(
    request: EnhanceRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Enhance location data with council, road classification, and combined authority."""
    # Get locations that need enhancement
    result = await db.execute(
        select(Location).where(
            Location.location_type_id == uuid.UUID(request.location_type_id),
            Location.is_enhanced == False
        )
    )
    locations = result.scalars().all()
    
    if not locations:
        return EnhanceResponse(
            message="No locations need enhancement",
            locations_enhanced=0,
            councils_found=[]
        )
    
    # Enhance locations
    enhancer = SpatialEnhancer(db)
    councils_found = set()
    enhanced_count = 0
    
    for location in locations:
        try:
            enhanced_data = await enhancer.enhance_location(
                location.latitude,
                location.longitude,
                enhance_council=request.enhance_council,
                enhance_road=request.enhance_road,
                enhance_authority=request.enhance_authority
            )
            
            if request.enhance_council and enhanced_data.get("council"):
                location.council = enhanced_data["council"]
                councils_found.add(enhanced_data["council"])
            
            if request.enhance_road and enhanced_data.get("road_classification"):
                location.road_classification = enhanced_data["road_classification"]
            
            if request.enhance_authority and enhanced_data.get("combined_authority"):
                location.combined_authority = enhanced_data["combined_authority"]
            
            location.is_enhanced = True
            enhanced_count += 1
            
        except Exception as e:
            # Log error but continue with other locations
            print(f"Error enhancing location {location.id}: {str(e)}")
    
    await db.commit()
    
    return EnhanceResponse(
        message=f"Enhanced {enhanced_count} locations",
        locations_enhanced=enhanced_count,
        councils_found=list(councils_found)
    )


@router.get("/councils/{location_type_id}")
async def get_councils(
    location_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get list of councils for a location type."""
    result = await db.execute(
        select(Location.council, func.count(Location.id).label("count"))
        .where(
            Location.location_type_id == location_type_id,
            Location.council.isnot(None)
        )
        .group_by(Location.council)
        .order_by(Location.council)
    )
    councils = result.all()
    
    return [
        {"council": c.council, "location_count": c.count}
        for c in councils
    ]

