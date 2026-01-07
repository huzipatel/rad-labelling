"""Google Cloud Storage service with organized folder structure."""
import os
from typing import Optional
from pathlib import Path
from datetime import datetime

from app.core.config import settings


class GCSStorage:
    """
    Handle file uploads to Google Cloud Storage with organized folder structure.
    
    Folder structure:
    - Images: {year}/{location_type}/{council}/{identifier}_{heading}_{date}.jpg
    - Exports: {year}/{location_type}/{council}/exports/{filename}
    """
    
    def __init__(self):
        self.bucket_name = settings.GCS_BUCKET_NAME
        self._client = None
        self._bucket = None
        self._use_local = not settings.GCS_CREDENTIALS_PATH
        self._local_storage_path = Path(settings.UPLOAD_DIR) / "images"
        
        # Create local storage directory if using local mode
        if self._use_local:
            self._local_storage_path.mkdir(parents=True, exist_ok=True)
            print(f"[GCSStorage] Using LOCAL storage at {self._local_storage_path}")
            print(f"[GCSStorage] To use GCS, set GCS_CREDENTIALS_PATH environment variable")
        else:
            print(f"[GCSStorage] Using Google Cloud Storage bucket: {self.bucket_name}")
    
    @property
    def client(self):
        """Get or create GCS client."""
        if self._use_local:
            return None
            
        if self._client is None:
            try:
                from google.cloud import storage
                from google.oauth2 import service_account
                
                if settings.GCS_CREDENTIALS_PATH and os.path.exists(settings.GCS_CREDENTIALS_PATH):
                    credentials = service_account.Credentials.from_service_account_file(
                        settings.GCS_CREDENTIALS_PATH
                    )
                    self._client = storage.Client(credentials=credentials)
                    print(f"[GCSStorage] Connected to GCS with service account")
                else:
                    # Try default credentials
                    self._client = storage.Client()
                    print(f"[GCSStorage] Connected to GCS with default credentials")
            except Exception as e:
                print(f"[GCSStorage] Failed to initialize GCS client: {e}")
                print(f"[GCSStorage] Falling back to local storage")
                self._use_local = True
                self._local_storage_path.mkdir(parents=True, exist_ok=True)
        return self._client
    
    @property
    def bucket(self):
        """Get or create bucket reference."""
        if self._use_local:
            return None
            
        if self._bucket is None and self.client:
            from google.cloud import storage
            self._bucket = self.client.bucket(self.bucket_name)
        return self._bucket
    
    def _build_organized_path(
        self,
        filename: str,
        location_type: Optional[str] = None,
        council: Optional[str] = None,
        subfolder: Optional[str] = None
    ) -> str:
        """
        Build an organized path for storage.
        
        Structure: {year}/{location_type}/{council}/{subfolder}/{filename}
        """
        year = datetime.now().strftime("%Y")
        
        # Sanitize folder names
        def sanitize(name: str) -> str:
            if not name:
                return "unknown"
            # Replace spaces and special characters
            return "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_")
        
        parts = [year]
        
        if location_type:
            parts.append(sanitize(location_type))
        else:
            parts.append("unspecified")
            
        if council:
            parts.append(sanitize(council))
        else:
            parts.append("unspecified")
        
        if subfolder:
            parts.append(sanitize(subfolder))
        
        parts.append(filename)
        
        return "/".join(parts)
    
    async def upload_image(
        self,
        data: bytes,
        filename: str,
        location_type: str,
        council: str,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Upload an image with organized folder structure.
        
        Args:
            data: Image bytes
            filename: Base filename (e.g., "identifier_heading_date.jpg")
            location_type: Location type name (e.g., "Bus Stops")
            council: Council name (e.g., "Birmingham")
            content_type: MIME type
        
        Returns:
            URL to access the image
        """
        organized_path = self._build_organized_path(
            filename=filename,
            location_type=location_type,
            council=council,
            subfolder="images"
        )
        
        return await self.upload_file(data, organized_path, content_type)
    
    async def upload_file(
        self,
        data: bytes,
        destination_path: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload a file to GCS or local storage.
        
        Args:
            data: File contents as bytes
            destination_path: Full path in the bucket
            content_type: MIME type of the file
        
        Returns:
            URL of the uploaded file
        """
        if self._use_local:
            # Save to local filesystem
            local_path = self._local_storage_path / destination_path
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data)
            # Return a relative URL that the backend will serve
            return f"/api/v1/images/{destination_path}"
        
        # Upload to GCS
        blob = self.bucket.blob(destination_path)
        blob.upload_from_string(data, content_type=content_type)
        
        # Make publicly readable (or use signed URLs)
        try:
            blob.make_public()
            return blob.public_url
        except Exception:
            # If we can't make it public, return the GCS URI
            return f"https://storage.googleapis.com/{self.bucket_name}/{destination_path}"
    
    async def upload_export(
        self,
        data: bytes,
        filename: str,
        location_type: str,
        council: str,
        content_type: str = "text/csv"
    ) -> str:
        """
        Upload an export file (CSV, etc.) with organized folder structure.
        """
        organized_path = self._build_organized_path(
            filename=filename,
            location_type=location_type,
            council=council,
            subfolder="exports"
        )
        
        return await self.upload_file(data, organized_path, content_type)
    
    async def download_file(self, source_path: str) -> bytes:
        """Download a file from GCS or local storage."""
        if self._use_local:
            local_path = self._local_storage_path / source_path
            if local_path.exists():
                return local_path.read_bytes()
            raise FileNotFoundError(f"File not found: {source_path}")
        
        blob = self.bucket.blob(source_path)
        return blob.download_as_bytes()
    
    async def delete_file(self, path: str) -> bool:
        """Delete a file from GCS or local storage."""
        if self._use_local:
            local_path = self._local_storage_path / path
            if local_path.exists():
                local_path.unlink()
                return True
            return False
        
        blob = self.bucket.blob(path)
        if blob.exists():
            blob.delete()
            return True
        return False
    
    async def list_files(self, prefix: str = "") -> list:
        """List files with optional prefix."""
        if self._use_local:
            base = self._local_storage_path / prefix
            if base.exists():
                return [str(f.relative_to(self._local_storage_path)) for f in base.rglob("*") if f.is_file()]
            return []
        
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        return [blob.name for blob in blobs]
    
    async def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        if self._use_local:
            return (self._local_storage_path / path).exists()
        
        blob = self.bucket.blob(path)
        return blob.exists()
    
    def get_public_url(self, path: str) -> str:
        """Get the public URL for a file."""
        if self._use_local:
            return f"/api/v1/images/{path}"
        return f"https://storage.googleapis.com/{self.bucket_name}/{path}"
