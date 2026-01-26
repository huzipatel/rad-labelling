"""Application configuration settings."""
from typing import List, Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "UK Advertising Labelling App"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_SECRET_KEY: str = "your-jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/labelling_db"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Google OAuth (for user login)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    
    # Backend URL (used for OAuth callbacks - set this in Render!)
    # Example: https://your-backend-service.onrender.com
    BACKEND_URL: str = ""
    
    @property
    def google_cloud_redirect_uri(self) -> str:
        """
        Get the Google Cloud OAuth redirect URI.
        Uses BACKEND_URL if set, otherwise falls back to localhost for local dev.
        """
        if self.BACKEND_URL:
            # Use the configured backend URL
            base = self.BACKEND_URL.rstrip("/")
            return f"{base}/api/v1/admin/gsv-oauth-callback"
        # Fallback for local development
        return "http://localhost:8000/api/v1/admin/gsv-oauth-callback"
    
    # Google Street View API
    # Single key (backwards compatible)
    GSV_API_KEY: str = ""
    # Multiple keys for rotation (comma-separated, e.g., "key1,key2,key3")
    GSV_API_KEYS: str = ""
    # Rate limiting settings - Google allows 30,000/min per key
    GSV_REQUESTS_PER_MINUTE: int = 5000  # Per key limit (conservative vs Google's 30k)
    GSV_DAILY_LIMIT_PER_KEY: int = 25000  # Google's daily limit for unsigned requests
    GSV_MIN_DELAY_MS: int = 10  # Minimum delay between requests in milliseconds
    
    @property
    def gsv_api_keys_list(self) -> List[str]:
        """Get list of all GSV API keys (combines single key and multiple keys)."""
        keys = []
        # Add single key if set
        if self.GSV_API_KEY:
            keys.append(self.GSV_API_KEY)
        # Add multiple keys if set
        if self.GSV_API_KEYS:
            for key in self.GSV_API_KEYS.split(","):
                key = key.strip()
                if key and key not in keys:
                    keys.append(key)
        return keys
    
    # Google Cloud Storage
    GCS_BUCKET_NAME: str = "labelling-images"
    GCS_CREDENTIALS_PATH: Optional[str] = None
    GCS_CREDENTIALS_JSON: Optional[str] = None  # JSON string for cloud deployments
    
    # Twilio WhatsApp
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""  # Twilio WhatsApp sandbox number (e.g., +14155238886)
    
    @property
    def TWILIO_WHATSAPP_FROM(self) -> str:
        """Alias for TWILIO_WHATSAPP_NUMBER for backwards compatibility."""
        return self.TWILIO_WHATSAPP_NUMBER
    
    # Email (SMTP)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    
    # Redis / Celery
    # Note: On Render, link the Key Value (Redis) service to set REDIS_URL
    # Celery will use REDIS_URL by default if CELERY_BROKER_URL/CELERY_RESULT_BACKEND aren't set
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: Optional[str] = None  # Falls back to REDIS_URL
    CELERY_RESULT_BACKEND: Optional[str] = None  # Falls back to REDIS_URL
    
    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL
    
    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # File Upload
    MAX_UPLOAD_SIZE: int = 200 * 1024 * 1024  # 200MB for spreadsheets
    MAX_SHAPEFILE_SIZE: int = 10 * 1024 * 1024 * 1024  # 10GB for shapefiles/geopackages
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".xls", ".csv"]
    ALLOWED_GEODATA_EXTENSIONS: List[str] = [".zip", ".gpkg"]
    
    # Upload directories
    UPLOAD_DIR: str = "/app/uploads"
    SHAPEFILE_DIR: str = "/app/uploads/shapefiles"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

