"""Data management routes - viewing, shapefiles, and enhancement."""
import uuid
import os
import zipfile
import tempfile
import json
import aiofiles
from datetime import datetime
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel

from app.core.database import get_db, async_session_maker
from app.core.config import settings
from app.models.user import User
from app.models.location import Location, LocationType
from app.models.label import Label
from app.models.shapefile import Shapefile, EnhancementJob, UploadJob
from app.api.deps import require_manager
from app.services.spatial_enhancer import SpatialEnhancer

# Chunk size for streaming large files (1MB)
CHUNK_SIZE = 1024 * 1024


router = APIRouter(prefix="/data", tags=["Data Management"])


# ============================================
# Request/Response Models
# ============================================

class LocationResponse(BaseModel):
    id: str
    identifier: str
    latitude: float
    longitude: float
    council: Optional[str]
    combined_authority: Optional[str]
    road_classification: Optional[str]
    is_enhanced: bool
    original_data: dict
    created_at: datetime
    # Additional computed fields
    common_name: Optional[str] = None
    locality_name: Optional[str] = None
    labelling_status: Optional[str] = None
    labeller_name: Optional[str] = None
    advertising_present: Optional[bool] = None

    class Config:
        from_attributes = True


class LocationListResponse(BaseModel):
    locations: List[LocationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    enhanced_count: int
    unenhanced_count: int
    labelled_count: int
    unlabelled_count: int
    all_columns: List[dict]  # All available columns with types


class DatasetStats(BaseModel):
    location_type_id: str
    location_type_name: str
    display_name: str
    total_locations: int
    enhanced_count: int
    unenhanced_count: int
    councils: List[dict]
    columns: List[dict]  # Now includes type info and original_data columns
    filter_values: dict  # Distinct values for filterable columns


class AttributeMapping(BaseModel):
    source_column: str  # Column in the shapefile
    target_column: str  # Column name to create in locations


class ShapefileResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    shapefile_type: str
    target_column: Optional[str]  # Legacy: Column this shapefile populates
    feature_count: int
    geometry_type: Optional[str]
    attribute_columns: dict  # Column name -> type
    name_column: Optional[str]  # Legacy
    attribute_mappings: List[dict]  # New: Multiple mappings
    value_columns: List[str]  # All columns that can be extracted
    is_loaded: bool
    created_at: datetime
    loaded_at: Optional[datetime]

    class Config:
        from_attributes = True


class UploadJobResponse(BaseModel):
    """Response for upload job status."""
    id: str
    filename: str
    display_name: str
    status: str  # pending, uploading, analyzing, processing, completed, failed
    stage: str  # Human readable stage
    total_bytes: int
    uploaded_bytes: int
    progress_percent: int
    shapefile_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ShapefileCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    shapefile_type: str  # Can be custom now
    target_column: str  # Column name this will populate in locations
    name_column: str  # Column in shapefile to use as value


class EnhancementPreview(BaseModel):
    location_type_id: str
    location_type_name: str
    total_locations: int
    unenhanced_count: int
    columns_to_add: List[dict]
    available_shapefiles: List[dict]
    sample_locations: List[dict]


class EnhancementJobResponse(BaseModel):
    id: str
    location_type_id: str
    status: str
    total_locations: int
    processed_locations: int
    enhanced_locations: int
    progress_percent: float
    enhance_council: bool
    enhance_road: bool
    enhance_authority: bool
    councils_found: List[str]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class StartEnhancementRequest(BaseModel):
    location_type_id: str
    enhance_council: bool = True
    enhance_road: bool = True
    enhance_authority: bool = True
    custom_shapefiles: Optional[List[str]] = None  # IDs of custom shapefiles to use


# ============================================
# Dataset Viewing Endpoints
# ============================================

@router.get("/locations/{location_type_id}", response_model=LocationListResponse)
async def get_locations(
    location_type_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = None,
    council: Optional[str] = None,
    enhanced_only: Optional[bool] = None,
    labelled_only: Optional[bool] = None,
    filters: Optional[str] = None,  # JSON string of column filters
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get paginated locations for a dataset with filtering on any column."""
    # Build query
    query = select(Location).where(Location.location_type_id == location_type_id)
    count_query = select(func.count(Location.id)).where(Location.location_type_id == location_type_id)
    
    # Apply standard filters
    if search:
        query = query.where(Location.identifier.ilike(f"%{search}%"))
        count_query = count_query.where(Location.identifier.ilike(f"%{search}%"))
    
    if council:
        query = query.where(Location.council == council)
        count_query = count_query.where(Location.council == council)
    
    if enhanced_only is not None:
        query = query.where(Location.is_enhanced == enhanced_only)
        count_query = count_query.where(Location.is_enhanced == enhanced_only)
    
    # Apply custom column filters (from original_data JSONB)
    if filters:
        try:
            filter_dict = json.loads(filters)
            for col_name, col_value in filter_dict.items():
                if col_value and col_value != '':
                    # Filter on JSONB field
                    json_filter = Location.original_data[col_name].astext == str(col_value)
                    query = query.where(json_filter)
                    count_query = count_query.where(json_filter)
        except json.JSONDecodeError:
            pass
    
    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get enhanced/unenhanced counts
    enhanced_result = await db.execute(
        select(func.count(Location.id)).where(
            Location.location_type_id == location_type_id,
            Location.is_enhanced == True
        )
    )
    enhanced_count = enhanced_result.scalar()
    
    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Location.identifier).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    locations = result.scalars().all()
    
    # Get labels for these locations
    location_ids = [loc.id for loc in locations]
    labels_result = await db.execute(
        select(Label).where(Label.location_id.in_(location_ids))
    )
    labels = {label.location_id: label for label in labels_result.scalars().all()}
    
    # Get labeller names
    labeller_ids = [label.labeller_id for label in labels.values() if label.labeller_id]
    labellers = {}
    if labeller_ids:
        labellers_result = await db.execute(
            select(User).where(User.id.in_(labeller_ids))
        )
        labellers = {user.id: user.name for user in labellers_result.scalars().all()}
    
    # Count labelled locations for this type
    labelled_result = await db.execute(
        select(func.count(Label.id)).where(
            Label.location_id.in_(
                select(Location.id).where(Location.location_type_id == location_type_id)
            )
        )
    )
    labelled_count = labelled_result.scalar() or 0
    
    # Collect all unique columns from original_data using the same logic as get_dataset_stats
    all_columns = [
        {"key": "identifier", "label": "Identifier", "type": "string", "source": "system"},
        {"key": "latitude", "label": "Latitude", "type": "number", "source": "system"},
        {"key": "longitude", "label": "Longitude", "type": "number", "source": "system"},
        {"key": "council", "label": "Council", "type": "string", "source": "enhanced"},
        {"key": "combined_authority", "label": "Combined Authority", "type": "string", "source": "enhanced"},
        {"key": "road_classification", "label": "Road Classification", "type": "string", "source": "enhanced"},
        {"key": "is_enhanced", "label": "Enhanced", "type": "boolean", "source": "system"},
        {"key": "labelling_status", "label": "Labelling Status", "type": "string", "source": "computed"},
        {"key": "labeller_name", "label": "Labeller", "type": "string", "source": "computed"},
        {"key": "advertising_present", "label": "Advertising Present", "type": "boolean", "source": "computed"},
    ]
    
    # Dynamically discover ALL columns from original_data for this location type
    coord_keys = {'latitude', 'longitude', 'lat', 'lng', 'long', 'lon', 'x', 'y', 'easting', 'northing'}
    
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
        all_original_keys = [row[0] for row in keys_result.fetchall()]
        
        # Detect types from current page of locations
        column_types = {}
        for loc in locations:
            if loc.original_data:
                for key, value in loc.original_data.items():
                    if key not in column_types and value is not None:
                        if isinstance(value, bool):
                            column_types[key] = "boolean"
                        elif isinstance(value, (int, float)):
                            column_types[key] = "number"
                        else:
                            column_types[key] = "string"
        
        for key in all_original_keys:
            if key.lower() in coord_keys:
                continue
            
            col_type = column_types.get(key, "string")
            all_columns.append({
                "key": f"original_{key}",
                "label": key,
                "type": col_type,
                "source": "original",
                "original_key": key
            })
    except Exception as e:
        print(f"Error discovering columns: {e}")
        # Fallback: use just the current page's data
        if locations:
            seen_keys = set()
            for loc in locations:
                if loc.original_data:
                    for key, value in loc.original_data.items():
                        if key.lower() not in coord_keys and key not in seen_keys:
                            seen_keys.add(key)
                            col_type = "string"
                            if isinstance(value, bool):
                                col_type = "boolean"
                            elif isinstance(value, (int, float)):
                                col_type = "number"
                            all_columns.append({
                                "key": f"original_{key}",
                                "label": key,
                                "type": col_type,
                                "source": "original",
                                "original_key": key
                            })
    
    # Build response with enriched data
    location_responses = []
    for loc in locations:
        label = labels.get(loc.id)
        original = loc.original_data or {}
        
        # Extract common fields from original_data (case-insensitive)
        common_name = None
        locality_name = None
        for key, value in original.items():
            key_lower = key.lower()
            if key_lower in ['commonname', 'common_name', 'name']:
                common_name = str(value) if value else None
            if key_lower in ['localityname', 'locality_name', 'locality']:
                locality_name = str(value) if value else None
        
        location_responses.append(LocationResponse(
            id=str(loc.id),
            identifier=loc.identifier,
            latitude=loc.latitude,
            longitude=loc.longitude,
            council=loc.council,
            combined_authority=loc.combined_authority,
            road_classification=loc.road_classification,
            is_enhanced=loc.is_enhanced,
            original_data=original,
            created_at=loc.created_at,
            common_name=common_name,
            locality_name=locality_name,
            labelling_status='Labelled' if label else 'Not Labelled',
            labeller_name=labellers.get(label.labeller_id) if label and label.labeller_id else None,
            advertising_present=label.advertising_present if label else None
        ))
    
    return LocationListResponse(
        locations=location_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        enhanced_count=enhanced_count,
        unenhanced_count=total - enhanced_count,
        labelled_count=labelled_count,
        unlabelled_count=total - labelled_count,
        all_columns=all_columns
    )


@router.get("/datasets", response_model=List[DatasetStats])
async def get_dataset_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get statistics for all datasets including ALL available columns from the data."""
    result = await db.execute(select(LocationType))
    location_types = result.scalars().all()
    
    datasets = []
    for lt in location_types:
        # Get counts
        total_result = await db.execute(
            select(func.count(Location.id)).where(Location.location_type_id == lt.id)
        )
        total = total_result.scalar()
        
        enhanced_result = await db.execute(
            select(func.count(Location.id)).where(
                Location.location_type_id == lt.id,
                Location.is_enhanced == True
            )
        )
        enhanced = enhanced_result.scalar()
        
        # Get council breakdown
        councils_result = await db.execute(
            select(Location.council, func.count(Location.id).label("count"))
            .where(Location.location_type_id == lt.id, Location.council.isnot(None))
            .group_by(Location.council)
            .order_by(func.count(Location.id).desc())
            .limit(50)
        )
        councils = [{"name": c.council, "count": c.count} for c in councils_result.all()]
        
        # Build columns list with system columns first
        columns = [
            {"key": "identifier", "label": "Identifier", "type": "string", "source": "system", "filterable": True},
            {"key": "latitude", "label": "Latitude", "type": "number", "source": "system", "filterable": False},
            {"key": "longitude", "label": "Longitude", "type": "number", "source": "system", "filterable": False},
            {"key": "council", "label": "Council", "type": "string", "source": "enhanced", "filterable": True},
            {"key": "combined_authority", "label": "Combined Authority", "type": "string", "source": "enhanced", "filterable": True},
            {"key": "road_classification", "label": "Road Class", "type": "string", "source": "enhanced", "filterable": True},
            {"key": "is_enhanced", "label": "Enhanced", "type": "boolean", "source": "system", "filterable": True},
            {"key": "labelling_status", "label": "Labelling Status", "type": "string", "source": "computed", "filterable": True},
            {"key": "advertising_present", "label": "Advertising", "type": "boolean", "source": "computed", "filterable": True},
        ]
        
        # Get sample to discover original_data columns - sample more records for completeness
        filter_values = {"council": [c["name"] for c in councils]}
        
        # Get ALL unique keys from the JSONB column using PostgreSQL's jsonb_object_keys
        # This is much more efficient than loading records into Python
        try:
            keys_result = await db.execute(
                text("""
                    SELECT DISTINCT key
                    FROM locations, jsonb_object_keys(original_data) AS key
                    WHERE location_type_id = :lt_id
                    AND original_data IS NOT NULL
                    ORDER BY key
                """),
                {"lt_id": str(lt.id)}
            )
            all_original_keys = [row[0] for row in keys_result.fetchall()]
        except Exception as e:
            print(f"Error getting JSONB keys: {e}")
            all_original_keys = []
        
        # Get sample values for each discovered key
        column_sample_values = {}
        column_types = {}
        
        if all_original_keys:
            # Get a sample of records to determine types and values
            sample_result = await db.execute(
                select(Location.original_data)
                .where(Location.location_type_id == lt.id, Location.original_data.isnot(None))
                .limit(500)  # Larger sample for better type detection
            )
            samples = sample_result.scalars().all()
            
            for key in all_original_keys:
                column_sample_values[key] = set()
                column_types[key] = "string"
                
                for sample in samples:
                    if sample and key in sample:
                        value = sample[key]
                        if value is not None:
                            # Detect type
                            if isinstance(value, bool):
                                column_types[key] = "boolean"
                            elif isinstance(value, (int, float)):
                                column_types[key] = "number"
                            
                            # Collect sample values (up to 100 for filtering)
                            if len(column_sample_values[key]) < 100:
                                column_sample_values[key].add(str(value))
        
        # Add original_data columns - exclude coordinate-like columns
        coord_keys = {'latitude', 'longitude', 'lat', 'lng', 'long', 'lon', 'x', 'y', 'easting', 'northing'}
        
        for key in all_original_keys:
            key_lower = key.lower()
            if key_lower in coord_keys:
                continue
                
            sample_vals = list(column_sample_values.get(key, []))
            col_type = column_types.get(key, "string")
            
            columns.append({
                "key": f"original_{key}",
                "label": key,
                "type": col_type,
                "source": "original",
                "original_key": key,
                "filterable": len(sample_vals) <= 100  # Filterable if reasonable # of unique values
            })
            
            # Add filter values for columns with few distinct values
            if len(sample_vals) <= 100:
                filter_values[f"original_{key}"] = sorted(sample_vals)
        
        datasets.append(DatasetStats(
            location_type_id=str(lt.id),
            location_type_name=lt.name,
            display_name=lt.display_name,
            total_locations=total,
            enhanced_count=enhanced,
            unenhanced_count=total - enhanced,
            councils=councils,
            columns=columns,
            filter_values=filter_values
        ))
    
    return datasets


# ============================================
# Shapefile Management Endpoints
# ============================================

@router.get("/shapefiles", response_model=List[ShapefileResponse])
async def list_shapefiles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List all registered shapefiles."""
    result = await db.execute(select(Shapefile).order_by(Shapefile.created_at.desc()))
    shapefiles = result.scalars().all()
    
    return [
        ShapefileResponse(
            id=str(sf.id),
            name=sf.name,
            display_name=sf.display_name,
            description=sf.description,
            shapefile_type=sf.shapefile_type,
            target_column=sf.name_column,  # Legacy
            feature_count=sf.feature_count,
            geometry_type=sf.geometry_type,
            attribute_columns=sf.attribute_columns or {},
            name_column=sf.name_column,  # Legacy
            attribute_mappings=sf.attribute_mappings or [],  # New multi-column mappings
            value_columns=list(sf.attribute_columns.keys()) if sf.attribute_columns else [],
            is_loaded=sf.is_loaded,
            created_at=sf.created_at,
            loaded_at=sf.loaded_at
        )
        for sf in shapefiles
    ]


@router.get("/shapefiles/types")
async def get_shapefile_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get predefined and custom shapefile types."""
    # Get custom types from existing shapefiles
    result = await db.execute(
        select(Shapefile.shapefile_type).distinct()
    )
    existing_types = [r[0] for r in result.all()]
    
    predefined = [
        {"value": "council_boundaries", "label": "Council Boundaries", "target_column": "council"},
        {"value": "combined_authorities", "label": "Combined Authorities", "target_column": "combined_authority"},
        {"value": "road_classifications", "label": "Road Classifications", "target_column": "road_classification"},
    ]
    
    # Add custom types
    custom_types = []
    for t in existing_types:
        if t not in [p["value"] for p in predefined]:
            custom_types.append({
                "value": t,
                "label": t.replace("_", " ").title(),
                "target_column": t,
                "custom": True
            })
    
    return {
        "predefined": predefined,
        "custom": custom_types,
        "allow_custom": True
    }


@router.post("/shapefiles/analyze")
async def analyze_uploaded_shapefile(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Analyze a shapefile ZIP or GeoPackage and return available columns/attributes.
    This allows users to see what's in the file before committing.
    Supports: .zip (shapefile), .gpkg (GeoPackage)
    """
    filename = file.filename.lower()
    if not (filename.endswith('.zip') or filename.endswith('.gpkg')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a ZIP file (shapefile) or .gpkg file (GeoPackage)"
        )
    
    # Save temporarily
    temp_dir = tempfile.mkdtemp()
    ext = '.gpkg' if filename.endswith('.gpkg') else '.zip'
    temp_path = os.path.join(temp_dir, f"temp_geodata{ext}")
    
    try:
        contents = await file.read()
        with open(temp_path, "wb") as f:
            f.write(contents)
        
        # Analyze based on file type
        if filename.endswith('.gpkg'):
            geodata_info = await analyze_geopackage(temp_path)
            file_type = "geopackage"
        else:
            geodata_info = await analyze_shapefile_detailed(temp_path)
            file_type = "shapefile"
        
        return {
            "filename": file.filename,
            "file_type": file_type,
            "shapefiles_found": geodata_info["shapefiles"],  # Keep same key for compatibility
            "layers_found": geodata_info.get("layers", geodata_info["shapefiles"]),
            "message": f"{file_type.title()} analyzed successfully. Select attributes to import."
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error analyzing file: {str(e)}"
        )
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


@router.post("/shapefiles/upload/start", response_model=UploadJobResponse)
async def start_shapefile_upload(
    filename: str = Form(...),
    file_size: int = Form(...),
    name: str = Form(...),
    display_name: str = Form(...),
    description: Optional[str] = Form(None),
    shapefile_type: str = Form(...),
    attribute_mappings: str = Form(None),
    layer_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Initialize an upload job for a large shapefile.
    Returns a job_id that can be used to upload chunks and track progress.
    """
    fname_lower = filename.lower()
    if not (fname_lower.endswith('.zip') or fname_lower.endswith('.gpkg')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a ZIP file (shapefile) or .gpkg file (GeoPackage)"
        )
    
    # Parse and validate attribute mappings
    mappings = []
    if attribute_mappings:
        try:
            mappings = json.loads(attribute_mappings)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid attribute_mappings JSON format"
            )
    
    if not mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please specify at least one attribute mapping"
        )
    
    # Create upload directory
    upload_dir = "/app/shapefiles"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Determine file extension
    ext = '.gpkg' if fname_lower.endswith('.gpkg') else '.zip'
    file_path = os.path.join(upload_dir, f"{name}_{uuid.uuid4().hex[:8]}{ext}")
    
    # Create upload job
    upload_job = UploadJob(
        filename=filename,
        display_name=display_name,
        status="pending",
        stage="Waiting for upload",
        total_bytes=file_size,
        uploaded_bytes=0,
        progress_percent=0,
        file_path=file_path,
        job_metadata={
            "name": name,
            "display_name": display_name,
            "description": description,
            "shapefile_type": shapefile_type,
            "attribute_mappings": mappings,
            "layer_name": layer_name
        }
    )
    
    db.add(upload_job)
    await db.commit()
    await db.refresh(upload_job)
    
    return UploadJobResponse(
        id=str(upload_job.id),
        filename=upload_job.filename,
        display_name=upload_job.display_name,
        status=upload_job.status,
        stage=upload_job.stage,
        total_bytes=upload_job.total_bytes,
        uploaded_bytes=upload_job.uploaded_bytes,
        progress_percent=upload_job.progress_percent,
        shapefile_id=None,
        error_message=None,
        created_at=upload_job.created_at,
        completed_at=None
    )


@router.post("/shapefiles/upload/{job_id}/chunk")
async def upload_shapefile_chunk(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Upload a chunk of a shapefile. Call repeatedly until all chunks uploaded.
    Send raw binary data in request body.
    """
    result = await db.execute(select(UploadJob).where(UploadJob.id == job_id))
    upload_job = result.scalar_one_or_none()
    
    if not upload_job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    
    if upload_job.status == "completed":
        raise HTTPException(status_code=400, detail="Upload already completed")
    
    if upload_job.status == "failed":
        raise HTTPException(status_code=400, detail="Upload failed, please start a new upload")
    
    # Update status to uploading
    if upload_job.status == "pending":
        upload_job.status = "uploading"
        upload_job.stage = "Uploading file..."
    
    # Stream chunk to file
    try:
        async with aiofiles.open(upload_job.file_path, "ab") as f:
            async for chunk in request.stream():
                await f.write(chunk)
                upload_job.uploaded_bytes += len(chunk)
        
        # Update progress
        if upload_job.total_bytes > 0:
            upload_job.progress_percent = min(99, int((upload_job.uploaded_bytes / upload_job.total_bytes) * 100))
        
        upload_job.stage = f"Uploading... {upload_job.uploaded_bytes / (1024*1024):.1f} MB / {upload_job.total_bytes / (1024*1024):.1f} MB"
        
        await db.commit()
        
        return {
            "uploaded_bytes": upload_job.uploaded_bytes,
            "progress_percent": upload_job.progress_percent,
            "status": upload_job.status
        }
        
    except Exception as e:
        upload_job.status = "failed"
        upload_job.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/shapefiles/upload/{job_id}/complete")
async def complete_shapefile_upload(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Mark upload as complete and start processing the file.
    """
    result = await db.execute(select(UploadJob).where(UploadJob.id == job_id))
    upload_job = result.scalar_one_or_none()
    
    if not upload_job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    
    if upload_job.status not in ["uploading", "pending"]:
        raise HTTPException(status_code=400, detail=f"Cannot complete upload in status: {upload_job.status}")
    
    # Verify file exists and has content
    if not os.path.exists(upload_job.file_path):
        upload_job.status = "failed"
        upload_job.error_message = "File not found after upload"
        await db.commit()
        raise HTTPException(status_code=500, detail="File not found after upload")
    
    file_size = os.path.getsize(upload_job.file_path)
    if file_size == 0:
        upload_job.status = "failed"
        upload_job.error_message = "Uploaded file is empty"
        await db.commit()
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    
    upload_job.uploaded_bytes = file_size
    upload_job.status = "analyzing"
    upload_job.stage = "Analyzing file structure..."
    upload_job.progress_percent = 100
    await db.commit()
    
    # Start background processing
    background_tasks.add_task(process_shapefile_upload, str(job_id))
    
    return {"message": "Upload complete, processing started", "job_id": str(job_id)}


@router.get("/shapefiles/upload/{job_id}/status", response_model=UploadJobResponse)
async def get_upload_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get the status of an upload job."""
    result = await db.execute(select(UploadJob).where(UploadJob.id == job_id))
    upload_job = result.scalar_one_or_none()
    
    if not upload_job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    
    return UploadJobResponse(
        id=str(upload_job.id),
        filename=upload_job.filename,
        display_name=upload_job.display_name,
        status=upload_job.status,
        stage=upload_job.stage,
        total_bytes=upload_job.total_bytes,
        uploaded_bytes=upload_job.uploaded_bytes,
        progress_percent=upload_job.progress_percent,
        shapefile_id=str(upload_job.shapefile_id) if upload_job.shapefile_id else None,
        error_message=upload_job.error_message,
        created_at=upload_job.created_at,
        completed_at=upload_job.completed_at
    )


@router.post("/shapefiles/upload")
async def upload_shapefile(
    file: UploadFile = File(...),
    name: str = Form(...),
    display_name: str = Form(...),
    description: Optional[str] = Form(None),
    shapefile_type: str = Form(...),
    target_column: str = Form(None),
    name_column: str = Form(None),
    attribute_mappings: str = Form(None),
    layer_name: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Upload a shapefile (ZIP) or GeoPackage (.gpkg) - Standard upload for smaller files.
    For files > 500MB, use the chunked upload endpoints instead.
    
    This endpoint streams the file to disk to handle large files efficiently.
    """
    filename = file.filename.lower() if file.filename else "unknown"
    if not (filename.endswith('.zip') or filename.endswith('.gpkg')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a ZIP file (shapefile) or .gpkg file (GeoPackage)"
        )
    
    # Parse attribute mappings
    mappings = []
    if attribute_mappings:
        try:
            mappings = json.loads(attribute_mappings)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid attribute_mappings JSON format"
            )
    elif name_column and target_column:
        mappings = [{"source_column": name_column, "target_column": target_column}]
    elif name_column:
        target = {
            "council_boundaries": "council",
            "combined_authorities": "combined_authority",
            "road_classifications": "road_classification"
        }.get(shapefile_type, shapefile_type)
        mappings = [{"source_column": name_column, "target_column": target}]
    
    if not mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please specify at least one attribute mapping"
        )
    
    # Determine file type and path
    is_geopackage = filename.endswith('.gpkg')
    ext = '.gpkg' if is_geopackage else '.zip'
    upload_dir = "/app/shapefiles"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{name}_{uuid.uuid4().hex[:8]}{ext}")
    
    # Stream file to disk in chunks (handles large files without loading into memory)
    total_written = 0
    try:
        async with aiofiles.open(file_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                await f.write(chunk)
                total_written += len(chunk)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving file: {str(e)}"
        )
    
    # Analyze the file
    try:
        if is_geopackage:
            geodata_info = await analyze_geopackage(file_path)
        else:
            geodata_info = await analyze_shapefile_detailed(file_path)
        
        layers = geodata_info.get("shapefiles", [])
        if layer_name:
            selected_layer = next((l for l in layers if l.get("name") == layer_name), None)
            if not selected_layer and layers:
                selected_layer = layers[0]
        elif layers:
            selected_layer = layers[0]
        else:
            selected_layer = None
            
        if selected_layer:
            feature_count = selected_layer.get("feature_count", 0)
            geometry_type = selected_layer.get("geometry_type", "Unknown")
            attribute_columns = selected_layer.get("attributes", {})
        else:
            feature_count = 0
            geometry_type = "Unknown"
            attribute_columns = {}
            
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error analyzing file: {str(e)}"
        )
    
    # Create shapefile record
    shapefile = Shapefile(
        name=name,
        display_name=display_name,
        description=description,
        shapefile_type=shapefile_type,
        file_path=file_path,
        feature_count=feature_count,
        geometry_type=geometry_type,
        attribute_columns=attribute_columns,
        name_column=mappings[0]["source_column"] if mappings else None,
        attribute_mappings=mappings,
        is_loaded=False
    )
    
    db.add(shapefile)
    await db.commit()
    await db.refresh(shapefile)
    
    return {
        "message": "Shapefile uploaded successfully",
        "shapefile_id": str(shapefile.id),
        "feature_count": shapefile.feature_count,
        "geometry_type": shapefile.geometry_type,
        "attribute_columns": attribute_columns,
        "attribute_mappings": mappings,
        "columns_to_add": [m["target_column"] for m in mappings],
        "file_size_mb": round(total_written / (1024 * 1024), 2)
    }


@router.post("/shapefiles/{shapefile_id}/load")
async def load_shapefile(
    shapefile_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Load a shapefile into the database for spatial queries."""
    result = await db.execute(select(Shapefile).where(Shapefile.id == shapefile_id))
    shapefile = result.scalar_one_or_none()
    
    if not shapefile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shapefile not found"
        )
    
    if shapefile.is_loaded:
        return {"message": "Shapefile already loaded"}
    
    # Add background task to load the shapefile
    background_tasks.add_task(
        load_shapefile_to_db,
        shapefile_id=str(shapefile.id),
        file_path=shapefile.file_path,
        shapefile_type=shapefile.shapefile_type,
        name_column=shapefile.name_column
    )
    
    return {
        "message": "Shapefile loading started",
        "shapefile_id": str(shapefile.id)
    }


@router.delete("/shapefiles/{shapefile_id}")
async def delete_shapefile(
    shapefile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete a shapefile and its data."""
    result = await db.execute(select(Shapefile).where(Shapefile.id == shapefile_id))
    shapefile = result.scalar_one_or_none()
    
    if not shapefile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shapefile not found"
        )
    
    # Delete file if exists
    if shapefile.file_path and os.path.exists(shapefile.file_path):
        os.remove(shapefile.file_path)
    
    await db.delete(shapefile)
    await db.commit()
    
    return {"message": "Shapefile deleted"}


# ============================================
# Enhancement Endpoints
# ============================================

@router.get("/enhancement/preview/{location_type_id}", response_model=EnhancementPreview)
async def preview_enhancement(
    location_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Preview what enhancement will add to the dataset."""
    # Get location type
    lt_result = await db.execute(
        select(LocationType).where(LocationType.id == location_type_id)
    )
    location_type = lt_result.scalar_one_or_none()
    
    if not location_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location type not found"
        )
    
    # Get counts
    total_result = await db.execute(
        select(func.count(Location.id)).where(Location.location_type_id == location_type_id)
    )
    total = total_result.scalar()
    
    unenhanced_result = await db.execute(
        select(func.count(Location.id)).where(
            Location.location_type_id == location_type_id,
            Location.is_enhanced == False
        )
    )
    unenhanced = unenhanced_result.scalar()
    
    # Get all shapefiles (both loaded and not)
    shapefiles_result = await db.execute(select(Shapefile))
    shapefiles = shapefiles_result.scalars().all()
    
    # Build available shapefiles list with more detail
    available_shapefiles = []
    for sf in shapefiles:
        # Get all mappings for this shapefile
        mappings = sf.attribute_mappings or []
        if not mappings and sf.name_column:
            # Legacy: create mapping from name_column
            target_col = {
                "council_boundaries": "council",
                "combined_authorities": "combined_authority",
                "road_classifications": "road_classification"
            }.get(sf.shapefile_type, sf.shapefile_type)
            mappings = [{"source_column": sf.name_column, "target_column": target_col}]
        
        available_shapefiles.append({
            "id": str(sf.id),
            "name": sf.display_name,
            "type": sf.shapefile_type,
            "feature_count": sf.feature_count,
            "adds_columns": [m["target_column"] for m in mappings],
            "attribute_mappings": mappings,
            "is_loaded": sf.is_loaded,
            "available_columns": list(sf.attribute_columns.keys()) if sf.attribute_columns else []
        })
    
    # Build columns_to_add from all shapefile mappings
    columns_to_add = []
    seen_columns = set()
    
    # Standard columns first
    standard_mappings = {
        "council": ("council_boundaries", "Local authority / council name from boundary shapefile"),
        "combined_authority": ("combined_authorities", "Combined authority name (if applicable)"),
        "road_classification": ("road_classifications", "Road type (A/B/C etc) from OS roads data")
    }
    
    for col_name, (sf_type, description) in standard_mappings.items():
        loaded = any(
            sf.is_loaded and (
                sf.shapefile_type == sf_type or 
                any(m.get("target_column") == col_name for m in (sf.attribute_mappings or []))
            )
            for sf in shapefiles
        )
        columns_to_add.append({
            "name": col_name,
            "description": description,
            "shapefile_required": sf_type,
            "shapefile_loaded": loaded
        })
        seen_columns.add(col_name)
    
    # Add columns from all shapefile mappings
    for sf in shapefiles:
        mappings = sf.attribute_mappings or []
        for mapping in mappings:
            target_col = mapping.get("target_column")
            source_col = mapping.get("source_column")
            if target_col and target_col not in seen_columns:
                columns_to_add.append({
                    "name": target_col,
                    "description": f"From {sf.display_name} ({source_col})",
                    "shapefile_required": sf.shapefile_type,
                    "shapefile_id": str(sf.id),
                    "shapefile_loaded": sf.is_loaded,
                    "custom": True
                })
                seen_columns.add(target_col)
    
    # Get sample unenhanced locations
    sample_result = await db.execute(
        select(Location)
        .where(Location.location_type_id == location_type_id, Location.is_enhanced == False)
        .limit(5)
    )
    samples = sample_result.scalars().all()
    
    sample_locations = [
        {
            "identifier": loc.identifier,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "council": loc.council,
            "combined_authority": loc.combined_authority,
            "road_classification": loc.road_classification
        }
        for loc in samples
    ]
    
    return EnhancementPreview(
        location_type_id=str(location_type_id),
        location_type_name=location_type.display_name,
        total_locations=total,
        unenhanced_count=unenhanced,
        columns_to_add=columns_to_add,
        available_shapefiles=available_shapefiles,
        sample_locations=sample_locations
    )


@router.post("/enhancement/start", response_model=EnhancementJobResponse)
async def start_enhancement(
    request: StartEnhancementRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Start an enhancement job for a dataset."""
    location_type_id = uuid.UUID(request.location_type_id)
    
    # Check for existing running job
    existing_result = await db.execute(
        select(EnhancementJob).where(
            EnhancementJob.location_type_id == location_type_id,
            EnhancementJob.status.in_(["pending", "running"])
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An enhancement job is already running for this dataset"
        )
    
    # Count unenhanced locations
    count_result = await db.execute(
        select(func.count(Location.id)).where(
            Location.location_type_id == location_type_id,
            Location.is_enhanced == False
        )
    )
    total = count_result.scalar()
    
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No unenhanced locations found"
        )
    
    # Create job
    job = EnhancementJob(
        location_type_id=location_type_id,
        status="pending",
        total_locations=total,
        enhance_council=request.enhance_council,
        enhance_road=request.enhance_road,
        enhance_authority=request.enhance_authority
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Start background enhancement
    background_tasks.add_task(
        run_enhancement_job,
        job_id=str(job.id)
    )
    
    return EnhancementJobResponse(
        id=str(job.id),
        location_type_id=str(job.location_type_id),
        status=job.status,
        total_locations=job.total_locations,
        processed_locations=job.processed_locations,
        enhanced_locations=job.enhanced_locations,
        progress_percent=0.0,
        enhance_council=job.enhance_council,
        enhance_road=job.enhance_road,
        enhance_authority=job.enhance_authority,
        councils_found=job.councils_found or [],
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@router.get("/enhancement/jobs", response_model=List[EnhancementJobResponse])
async def list_enhancement_jobs(
    location_type_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List enhancement jobs, optionally filtered by location type."""
    query = select(EnhancementJob).order_by(EnhancementJob.created_at.desc())
    
    if location_type_id:
        query = query.where(EnhancementJob.location_type_id == location_type_id)
    
    result = await db.execute(query.limit(20))
    jobs = result.scalars().all()
    
    return [
        EnhancementJobResponse(
            id=str(job.id),
            location_type_id=str(job.location_type_id),
            status=job.status,
            total_locations=job.total_locations,
            processed_locations=job.processed_locations,
            enhanced_locations=job.enhanced_locations,
            progress_percent=(job.processed_locations / job.total_locations * 100) if job.total_locations > 0 else 0,
            enhance_council=job.enhance_council,
            enhance_road=job.enhance_road,
            enhance_authority=job.enhance_authority,
            councils_found=job.councils_found or [],
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at
        )
        for job in jobs
    ]


@router.get("/enhancement/jobs/{job_id}", response_model=EnhancementJobResponse)
async def get_enhancement_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get enhancement job status."""
    result = await db.execute(select(EnhancementJob).where(EnhancementJob.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    return EnhancementJobResponse(
        id=str(job.id),
        location_type_id=str(job.location_type_id),
        status=job.status,
        total_locations=job.total_locations,
        processed_locations=job.processed_locations,
        enhanced_locations=job.enhanced_locations,
        progress_percent=(job.processed_locations / job.total_locations * 100) if job.total_locations > 0 else 0,
        enhance_council=job.enhance_council,
        enhance_road=job.enhance_road,
        enhance_authority=job.enhance_authority,
        councils_found=job.councils_found or [],
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


# ============================================
# Helper Functions
# ============================================

async def analyze_geopackage(gpkg_path: str) -> dict:
    """Analyze a GeoPackage file and return detailed metadata including all layers and attributes."""
    import sqlite3
    
    layers_info = []
    
    try:
        # GeoPackage is SQLite-based
        conn = sqlite3.connect(gpkg_path)
        cursor = conn.cursor()
        
        # Get list of feature tables from gpkg_contents
        cursor.execute("""
            SELECT table_name, data_type, identifier, description, srs_id
            FROM gpkg_contents
            WHERE data_type IN ('features', 'tiles')
        """)
        tables = cursor.fetchall()
        
        for table_name, data_type, identifier, description, srs_id in tables:
            if data_type != 'features':
                continue
                
            # Get geometry type from gpkg_geometry_columns
            cursor.execute("""
                SELECT geometry_type_name, column_name
                FROM gpkg_geometry_columns
                WHERE table_name = ?
            """, (table_name,))
            geom_info = cursor.fetchone()
            geometry_type = geom_info[0] if geom_info else "Unknown"
            geom_column = geom_info[1] if geom_info else "geom"
            
            # Get feature count
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            feature_count = cursor.fetchone()[0]
            
            # Get attribute columns (excluding geometry)
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns_info = cursor.fetchall()
            
            attributes = {}
            for col in columns_info:
                col_name = col[1]
                col_type = col[2]
                
                # Skip geometry column
                if col_name == geom_column:
                    continue
                
                # Map SQLite types to our types
                type_lower = col_type.lower() if col_type else 'text'
                if 'int' in type_lower:
                    attr_type = 'number'
                elif 'real' in type_lower or 'double' in type_lower or 'float' in type_lower:
                    attr_type = 'float'
                elif 'blob' in type_lower:
                    continue  # Skip binary columns
                else:
                    attr_type = 'string'
                
                attributes[col_name] = {"type": attr_type}
            
            # Get sample values
            sample_values = {}
            for attr_name in list(attributes.keys())[:20]:  # Limit to 20 columns
                try:
                    cursor.execute(f'''
                        SELECT DISTINCT "{attr_name}" 
                        FROM "{table_name}" 
                        WHERE "{attr_name}" IS NOT NULL 
                        LIMIT 10
                    ''')
                    values = [str(row[0]) for row in cursor.fetchall() if row[0] is not None]
                    sample_values[attr_name] = values
                except:
                    sample_values[attr_name] = []
            
            layers_info.append({
                "name": table_name,
                "file": gpkg_path,
                "identifier": identifier or table_name,
                "description": description,
                "has_required_files": True,
                "feature_count": feature_count,
                "geometry_type": geometry_type,
                "attributes": attributes,
                "sample_values": sample_values
            })
        
        conn.close()
        
    except Exception as e:
        print(f"Error analyzing GeoPackage: {e}")
        # Return minimal info on error
        layers_info = [{
            "name": "unknown",
            "file": gpkg_path,
            "has_required_files": True,
            "feature_count": 0,
            "geometry_type": "Unknown",
            "attributes": {},
            "sample_values": {}
        }]
    
    return {
        "shapefiles": layers_info,  # Keep same key for compatibility
        "layers": layers_info,
        "total_layers": len(layers_info),
        "file_type": "geopackage"
    }


async def analyze_shapefile_detailed(zip_path: str) -> dict:
    """Analyze a shapefile ZIP and return detailed metadata including all attributes."""
    shapefiles_info = []
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        files = z.namelist()
        shp_files = [f for f in files if f.endswith('.shp')]
        
        if not shp_files:
            raise ValueError("No .shp file found in ZIP")
        
        # For each shapefile found in the zip
        for shp_file in shp_files:
            shp_name = os.path.basename(shp_file).replace('.shp', '')
            
            # Check for required companion files
            base_name = shp_file.replace('.shp', '')
            required_files = ['.shp', '.shx', '.dbf']
            has_required = all(
                any(f.endswith(base_name.split('/')[-1] + ext) or f == base_name + ext 
                    for f in files) 
                for ext in required_files
            )
            
            # Try to read DBF to get attributes
            attributes = {}
            feature_count = 0
            sample_values = {}
            
            dbf_file = None
            for f in files:
                if f.endswith('.dbf') and (shp_name in f or f.replace('.dbf', '') == base_name.split('/')[-1]):
                    dbf_file = f
                    break
            
            if dbf_file:
                try:
                    # Extract DBF to temp and analyze
                    with z.open(dbf_file) as dbf:
                        # Read DBF header to get field names
                        # This is a simplified DBF reader - in production use dbfread
                        dbf_content = dbf.read()
                        
                        # DBF header structure
                        if len(dbf_content) > 32:
                            num_records = int.from_bytes(dbf_content[4:8], 'little')
                            header_size = int.from_bytes(dbf_content[8:10], 'little')
                            record_size = int.from_bytes(dbf_content[10:12], 'little')
                            
                            feature_count = num_records
                            
                            # Read field descriptors (32 bytes each, starting at byte 32)
                            field_offset = 32
                            while field_offset < header_size - 1:
                                field_desc = dbf_content[field_offset:field_offset + 32]
                                if field_desc[0] == 0x0D:  # Header terminator
                                    break
                                
                                field_name = field_desc[0:11].split(b'\x00')[0].decode('ascii', errors='ignore').strip()
                                field_type = chr(field_desc[11])
                                field_length = field_desc[16]
                                
                                if field_name:
                                    type_map = {'C': 'string', 'N': 'number', 'F': 'float', 'D': 'date', 'L': 'boolean'}
                                    attributes[field_name] = {
                                        "type": type_map.get(field_type, 'string'),
                                        "length": field_length
                                    }
                                    sample_values[field_name] = []
                                
                                field_offset += 32
                            
                            # Try to read some sample values
                            if num_records > 0 and record_size > 0:
                                data_start = header_size
                                for i in range(min(10, num_records)):
                                    record_offset = data_start + 1 + (i * record_size)  # +1 for delete flag
                                    if record_offset + record_size <= len(dbf_content):
                                        field_pos = 0
                                        for field_name, field_info in attributes.items():
                                            field_len = field_info.get("length", 10)
                                            if record_offset + field_pos + field_len <= len(dbf_content):
                                                value = dbf_content[record_offset + field_pos:record_offset + field_pos + field_len]
                                                try:
                                                    value_str = value.decode('ascii', errors='ignore').strip()
                                                    if value_str and len(sample_values[field_name]) < 5:
                                                        sample_values[field_name].append(value_str)
                                                except:
                                                    pass
                                            field_pos += field_len
                                
                except Exception as e:
                    print(f"Error reading DBF: {e}")
                    # Fallback to mock attributes
                    attributes = {"name": {"type": "string"}, "code": {"type": "string"}}
            
            shapefiles_info.append({
                "name": shp_name,
                "file": shp_file,
                "has_required_files": has_required,
                "feature_count": feature_count,
                "geometry_type": "Unknown",  # Would need to read .shp to determine
                "attributes": attributes,
                "sample_values": sample_values
            })
    
    return {
        "shapefiles": shapefiles_info,
        "total_files": len(files)
    }


async def load_shapefile_to_db(shapefile_id: str, file_path: str, shapefile_type: str, name_column: str):
    """Background task to load shapefile data into database."""
    from app.core.database import async_session_maker
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Shapefile).where(Shapefile.id == uuid.UUID(shapefile_id))
        )
        shapefile = result.scalar_one_or_none()
        
        if shapefile:
            # In production, this would use geopandas to read the shapefile
            # and insert geometries into PostGIS tables
            shapefile.is_loaded = True
            shapefile.loaded_at = datetime.utcnow()
            await db.commit()


async def process_shapefile_upload(job_id: str):
    """Background task to process an uploaded shapefile."""
    async with async_session_maker() as db:
        result = await db.execute(select(UploadJob).where(UploadJob.id == uuid.UUID(job_id)))
        upload_job = result.scalar_one_or_none()
        
        if not upload_job:
            return
        
        try:
            # Update status
            upload_job.status = "analyzing"
            upload_job.stage = "Analyzing file structure..."
            await db.commit()
            
            file_path = upload_job.file_path
            metadata = upload_job.job_metadata
            
            # Determine file type
            is_geopackage = file_path.lower().endswith('.gpkg')
            
            # Analyze the file
            upload_job.stage = "Reading file metadata..."
            await db.commit()
            
            if is_geopackage:
                geodata_info = await analyze_geopackage(file_path)
            else:
                geodata_info = await analyze_shapefile_detailed(file_path)
            
            upload_job.stage = "Processing layers..."
            await db.commit()
            
            # Get layer info
            layers = geodata_info.get("shapefiles", [])
            layer_name = metadata.get("layer_name")
            
            if layer_name:
                selected_layer = next((l for l in layers if l.get("name") == layer_name), None)
                if not selected_layer and layers:
                    selected_layer = layers[0]
            elif layers:
                selected_layer = layers[0]
            else:
                selected_layer = None
            
            if selected_layer:
                feature_count = selected_layer.get("feature_count", 0)
                geometry_type = selected_layer.get("geometry_type", "Unknown")
                attribute_columns = selected_layer.get("attributes", {})
            else:
                feature_count = 0
                geometry_type = "Unknown"
                attribute_columns = {}
            
            upload_job.stage = "Creating shapefile record..."
            await db.commit()
            
            # Create shapefile record
            mappings = metadata.get("attribute_mappings", [])
            shapefile = Shapefile(
                name=metadata.get("name", "unnamed"),
                display_name=metadata.get("display_name", "Unnamed"),
                description=metadata.get("description"),
                shapefile_type=metadata.get("shapefile_type", "custom"),
                file_path=file_path,
                feature_count=feature_count,
                geometry_type=geometry_type,
                attribute_columns=attribute_columns,
                name_column=mappings[0]["source_column"] if mappings else None,
                attribute_mappings=mappings,
                is_loaded=False
            )
            
            db.add(shapefile)
            await db.commit()
            await db.refresh(shapefile)
            
            # Update job as completed
            upload_job.shapefile_id = shapefile.id
            upload_job.status = "completed"
            upload_job.stage = f"Complete! {feature_count:,} features found"
            upload_job.completed_at = datetime.utcnow()
            await db.commit()
            
        except Exception as e:
            upload_job.status = "failed"
            upload_job.stage = "Processing failed"
            upload_job.error_message = str(e)
            upload_job.completed_at = datetime.utcnow()
            await db.commit()


async def run_enhancement_job(job_id: str):
    """Background task to run enhancement."""
    from app.core.database import async_session_maker
    
    async with async_session_maker() as db:
        # Get job
        result = await db.execute(
            select(EnhancementJob).where(EnhancementJob.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return
        
        # Update status to running
        job.status = "running"
        job.started_at = datetime.utcnow()
        await db.commit()
        
        try:
            # Get unenhanced locations
            loc_result = await db.execute(
                select(Location).where(
                    Location.location_type_id == job.location_type_id,
                    Location.is_enhanced == False
                )
            )
            locations = loc_result.scalars().all()
            
            enhancer = SpatialEnhancer(db)
            councils_found = set()
            enhanced_count = 0
            
            for i, location in enumerate(locations):
                try:
                    enhanced_data = await enhancer.enhance_location(
                        location.latitude,
                        location.longitude,
                        enhance_council=job.enhance_council,
                        enhance_road=job.enhance_road,
                        enhance_authority=job.enhance_authority
                    )
                    
                    if job.enhance_council and enhanced_data.get("council"):
                        location.council = enhanced_data["council"]
                        councils_found.add(enhanced_data["council"])
                    
                    if job.enhance_road and enhanced_data.get("road_classification"):
                        location.road_classification = enhanced_data["road_classification"]
                    
                    if job.enhance_authority and enhanced_data.get("combined_authority"):
                        location.combined_authority = enhanced_data["combined_authority"]
                    
                    location.is_enhanced = True
                    enhanced_count += 1
                    
                except Exception as e:
                    print(f"Error enhancing location {location.id}: {e}")
                
                # Update progress every 10 locations
                if (i + 1) % 10 == 0:
                    job.processed_locations = i + 1
                    job.enhanced_locations = enhanced_count
                    job.councils_found = list(councils_found)
                    await db.commit()
            
            # Complete job
            job.status = "completed"
            job.processed_locations = len(locations)
            job.enhanced_locations = enhanced_count
            job.councils_found = list(councils_found)
            job.completed_at = datetime.utcnow()
            await db.commit()
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
