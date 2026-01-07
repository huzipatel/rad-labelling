"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api.routes import auth, users, spreadsheets, tasks, labelling, exports, admin, data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="UK Advertising Location Labelling Application API",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(spreadsheets.router, prefix=settings.API_V1_PREFIX)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX)
app.include_router(labelling.router, prefix=settings.API_V1_PREFIX)
app.include_router(exports.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(data.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Render and other cloud platforms."""
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/api/v1/images/{path:path}")
async def serve_image(path: str):
    """
    Serve locally stored images.
    
    Handles both old format (gsv/filename.jpg) and new organized format
    (year/location_type/council/images/filename.jpg)
    """
    base_path = Path("/app/uploads/images")
    image_path = base_path / path
    
    if image_path.exists():
        return FileResponse(image_path, media_type="image/jpeg")
    
    # Try alternative paths for backwards compatibility
    alt_paths = [
        base_path / path.lstrip("/"),
        base_path / "gsv" / Path(path).name,  # Try in old gsv folder
        Path("/app/uploads") / path,
    ]
    
    for alt in alt_paths:
        if alt.exists():
            return FileResponse(alt, media_type="image/jpeg")
    
    # Log for debugging
    print(f"[Image 404] Path: {path}")
    print(f"[Image 404] Tried: {image_path}")
    
    raise HTTPException(status_code=404, detail=f"Image not found: {path}")


@app.get("/api/v1/debug/config")
async def debug_config():
    """Debug endpoint to check configuration (remove in production)."""
    return {
        "gsv_api_key_configured": bool(settings.GSV_API_KEY),
        "gsv_api_key_preview": settings.GSV_API_KEY[:10] + "..." if settings.GSV_API_KEY else None,
        "gcs_configured": bool(settings.GCS_CREDENTIALS_PATH),
        "gcs_bucket": settings.GCS_BUCKET_NAME,
        "upload_dir": settings.UPLOAD_DIR,
    }


@app.get("/api/v1/debug/images")
async def debug_images():
    """Debug endpoint to check image storage."""
    image_dir = Path("/app/uploads/images")
    gsv_dir = image_dir / "gsv"
    
    # Check directories exist
    dirs_exist = {
        "uploads_images": image_dir.exists(),
        "uploads_images_gsv": gsv_dir.exists()
    }
    
    # Count files
    file_counts = {}
    sample_files = []
    if image_dir.exists():
        file_counts["total_in_uploads"] = sum(1 for _ in image_dir.rglob("*") if _.is_file())
    if gsv_dir.exists():
        jpg_files = list(gsv_dir.glob("*.jpg"))
        file_counts["total_in_gsv"] = len(jpg_files)
        sample_files = [f.name for f in jpg_files[:10]]
    
    return {
        "directories": dirs_exist,
        "file_counts": file_counts,
        "sample_gsv_files": sample_files,
        "image_base_path": str(image_dir),
        "sample_urls": [f"/api/v1/images/gsv/{f}" for f in sample_files[:5]]
    }


@app.get("/api/v1/debug/image-db")
async def debug_image_db():
    """Debug endpoint to check image database entries."""
    from app.core.database import async_session_maker
    from sqlalchemy import select, text
    
    async with async_session_maker() as db:
        # Get count of images
        result = await db.execute(text("SELECT COUNT(*) FROM gsv_images"))
        count = result.scalar()
        
        # Get sample URLs
        result = await db.execute(text("SELECT gcs_url, gcs_path FROM gsv_images LIMIT 5"))
        samples = [{"gcs_url": row[0], "gcs_path": row[1]} for row in result.fetchall()]
        
        return {
            "total_images_in_db": count,
            "sample_entries": samples
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )

