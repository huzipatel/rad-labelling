"""
GSV API Key Manager with randomized selection and database persistence.

Manages multiple Google Street View API keys with:
- Random key selection (not round-robin) to avoid patterns
- Weighted selection (prefer keys with fewer requests)
- Randomized delays (jitter) between requests
- Database persistence for usage tracking
- Automatic quota exhaustion detection
"""
import asyncio
import random
import time
from datetime import datetime, date
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class KeyStats:
    """In-memory statistics for a single API key."""
    key: str
    db_id: str
    label: Optional[str] = None
    requests_today: int = 0
    requests_total: int = 0
    last_request_time: float = 0
    last_error_time: Optional[float] = None
    consecutive_errors: int = 0
    quota_exhausted: bool = False
    is_active: bool = True
    last_reset_date: date = field(default_factory=date.today)
    
    def reset_if_new_day(self) -> bool:
        """Reset daily counters if it's a new day. Returns True if reset occurred."""
        today = date.today()
        if self.last_reset_date != today:
            self.requests_today = 0
            self.quota_exhausted = False
            self.consecutive_errors = 0
            self.last_reset_date = today
            print(f"[GSV KeyManager] Reset daily counters for key {self.key[:12]}...")
            return True
        return False
    
    def is_usable(self) -> bool:
        """Check if this key can be used."""
        return self.is_active and not self.quota_exhausted


class GSVKeyManager:
    """
    Manages multiple GSV API keys with randomized selection and database persistence.
    
    Features:
    - Random weighted key selection (prefer keys with fewer daily requests)
    - Randomized delays (jitter) between requests for natural patterns
    - Database persistence for usage tracking across restarts
    - Automatic quota exhaustion detection (5+ consecutive 403s)
    - Thread-safe for concurrent access
    """
    
    _instance: Optional['GSVKeyManager'] = None
    _lock = Lock()
    
    # Configuration
    DAILY_LIMIT_PER_KEY = 25000  # Google's limit
    MIN_DELAY_MS = 50  # Minimum delay between requests
    MAX_DELAY_MS = 200  # Maximum delay (jitter range)
    QUOTA_ERROR_THRESHOLD = 5  # Consecutive 403s before marking quota exhausted
    
    def __new__(cls):
        """Singleton pattern for global key management."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._keys: Dict[str, KeyStats] = {}  # api_key -> KeyStats
        self._request_lock = asyncio.Lock()
        self._sync_lock = Lock()
        self._last_db_sync = 0
        self._db_sync_interval = 60  # Sync to DB every 60 seconds
        
        print("[GSV KeyManager] Initialized (keys will be loaded from database)")
    
    @property
    def total_keys(self) -> int:
        """Number of configured API keys."""
        return len(self._keys)
    
    @property
    def available_keys(self) -> int:
        """Number of keys that are currently usable."""
        count = 0
        for stats in self._keys.values():
            stats.reset_if_new_day()
            if stats.is_usable():
                count += 1
        return count
    
    async def load_keys_from_db(self, db: AsyncSession) -> int:
        """
        Load API keys from database.
        Call this on startup and periodically to sync.
        
        Returns the number of keys loaded.
        """
        from app.models.gsv_api_key import GSVApiKey
        
        result = await db.execute(
            select(GSVApiKey).where(GSVApiKey.is_active == True)
        )
        db_keys = result.scalars().all()
        
        with self._sync_lock:
            # Update existing keys and add new ones
            current_keys = set(self._keys.keys())
            db_key_set = set()
            
            for db_key in db_keys:
                api_key = db_key.api_key
                db_key_set.add(api_key)
                
                if api_key in self._keys:
                    # Update existing key stats from DB
                    stats = self._keys[api_key]
                    stats.is_active = db_key.is_active
                    stats.quota_exhausted = db_key.quota_exhausted
                    stats.label = db_key.label
                    # Don't overwrite in-memory request counts - they're more current
                else:
                    # Add new key
                    self._keys[api_key] = KeyStats(
                        key=api_key,
                        db_id=str(db_key.id),
                        label=db_key.label,
                        requests_today=db_key.requests_today,
                        requests_total=db_key.requests_total,
                        quota_exhausted=db_key.quota_exhausted,
                        is_active=db_key.is_active,
                        last_reset_date=db_key.last_reset_date or date.today(),
                    )
            
            # Remove keys that are no longer in DB
            for key in current_keys - db_key_set:
                del self._keys[key]
                print(f"[GSV KeyManager] Removed key {key[:12]}... (deleted from DB)")
        
        print(f"[GSV KeyManager] Loaded {len(self._keys)} active key(s) from database")
        return len(self._keys)
    
    async def sync_stats_to_db(self, db: AsyncSession) -> None:
        """Sync in-memory stats back to database."""
        from app.models.gsv_api_key import GSVApiKey
        
        now = time.time()
        if now - self._last_db_sync < self._db_sync_interval:
            return  # Too soon to sync
        
        self._last_db_sync = now
        
        for api_key, stats in self._keys.items():
            await db.execute(
                update(GSVApiKey)
                .where(GSVApiKey.api_key == api_key)
                .values(
                    requests_today=stats.requests_today,
                    requests_total=stats.requests_total,
                    last_used_at=datetime.utcnow() if stats.last_request_time > 0 else None,
                    consecutive_errors=stats.consecutive_errors,
                    quota_exhausted=stats.quota_exhausted,
                    last_reset_date=stats.last_reset_date,
                )
            )
        
        await db.commit()
    
    def get_status(self) -> Dict:
        """Get current status of all keys."""
        status = {
            "total_keys": self.total_keys,
            "available_keys": self.available_keys,
            "keys": []
        }
        
        for key, stats in self._keys.items():
            stats.reset_if_new_day()
            status["keys"].append({
                "key_prefix": key[:12] + "...",
                "label": stats.label,
                "requests_today": stats.requests_today,
                "requests_total": stats.requests_total,
                "quota_exhausted": stats.quota_exhausted,
                "is_active": stats.is_active,
                "consecutive_errors": stats.consecutive_errors,
                "status": "exhausted" if stats.quota_exhausted else ("active" if stats.is_usable() else "disabled")
            })
        
        return status
    
    async def get_key(self) -> Optional[str]:
        """
        Get an available API key using weighted random selection.
        
        Keys with fewer requests today are more likely to be selected,
        which helps distribute load evenly across all keys.
        
        Returns None if all keys are exhausted.
        """
        if not self._keys:
            return None
        
        async with self._request_lock:
            # Get all usable keys with their weights
            usable_keys: List[Tuple[str, float]] = []
            
            for key, stats in self._keys.items():
                stats.reset_if_new_day()
                
                if not stats.is_usable():
                    continue
                
                # Check if recently errored - wait 60s before retrying
                if stats.last_error_time and time.time() - stats.last_error_time < 60:
                    if stats.consecutive_errors >= 3:
                        continue  # Skip keys with recent errors
                
                # Weight: prefer keys with fewer requests today
                # Higher weight = more likely to be selected
                remaining_capacity = max(1, self.DAILY_LIMIT_PER_KEY - stats.requests_today)
                weight = remaining_capacity / self.DAILY_LIMIT_PER_KEY
                usable_keys.append((key, weight))
            
            if not usable_keys:
                print("[GSV KeyManager] All API keys are exhausted or disabled!")
                return None
            
            # Weighted random selection
            total_weight = sum(w for _, w in usable_keys)
            r = random.random() * total_weight
            
            cumulative = 0
            for key, weight in usable_keys:
                cumulative += weight
                if r <= cumulative:
                    return key
            
            # Fallback to last key if floating point issues
            return usable_keys[-1][0]
    
    async def record_request(
        self, 
        key: str, 
        success: bool = True, 
        status_code: int = 200,
        error_message: Optional[str] = None
    ):
        """
        Record a request result for tracking.
        
        Args:
            key: The API key used
            success: Whether the request was successful
            status_code: HTTP status code from the response
            error_message: Error message if failed
        """
        if key not in self._keys:
            return
        
        async with self._request_lock:
            stats = self._keys[key]
            stats.requests_today += 1
            stats.requests_total += 1
            stats.last_request_time = time.time()
            
            if status_code == 403 or status_code == 429:
                stats.consecutive_errors += 1
                stats.last_error_time = time.time()
                
                # After threshold consecutive errors, mark as quota exhausted
                if stats.consecutive_errors >= self.QUOTA_ERROR_THRESHOLD:
                    stats.quota_exhausted = True
                    print(f"[GSV KeyManager] Key {key[:12]}... marked as QUOTA EXHAUSTED after {stats.consecutive_errors} errors")
                else:
                    print(f"[GSV KeyManager] Key {key[:12]}... error #{stats.consecutive_errors} (status {status_code})")
            
            elif success and status_code == 200:
                # Reset error counter on success
                stats.consecutive_errors = 0
                
                # Check if approaching daily limit
                if stats.requests_today >= self.DAILY_LIMIT_PER_KEY:
                    stats.quota_exhausted = True
                    print(f"[GSV KeyManager] Key {key[:12]}... reached daily limit of {self.DAILY_LIMIT_PER_KEY}")
    
    async def apply_jitter(self):
        """
        Apply randomized delay between requests.
        
        Uses random delay between MIN_DELAY_MS and MAX_DELAY_MS to
        simulate natural user behavior and avoid detection patterns.
        """
        delay_ms = random.randint(self.MIN_DELAY_MS, self.MAX_DELAY_MS)
        delay_seconds = delay_ms / 1000.0
        await asyncio.sleep(delay_seconds)
    
    def force_reset_key(self, key_prefix: str) -> bool:
        """Force reset a key's error/quota status (admin function)."""
        for key, stats in self._keys.items():
            if key.startswith(key_prefix):
                stats.quota_exhausted = False
                stats.consecutive_errors = 0
                stats.last_error_time = None
                print(f"[GSV KeyManager] Force reset key {key[:12]}...")
                return True
        return False
    
    def add_key_to_memory(self, api_key: str, db_id: str, label: Optional[str] = None):
        """Add a new key to in-memory cache (call after DB insert)."""
        with self._sync_lock:
            if api_key not in self._keys:
                self._keys[api_key] = KeyStats(
                    key=api_key,
                    db_id=db_id,
                    label=label,
                )
                print(f"[GSV KeyManager] Added key {api_key[:12]}... to memory")
    
    def remove_key_from_memory(self, api_key: str):
        """Remove a key from in-memory cache (call after DB delete)."""
        with self._sync_lock:
            if api_key in self._keys:
                del self._keys[api_key]
                print(f"[GSV KeyManager] Removed key {api_key[:12]}... from memory")
    
    def get_daily_capacity(self) -> int:
        """Get total daily capacity across all active keys."""
        return self.available_keys * self.DAILY_LIMIT_PER_KEY


# Global instance
gsv_key_manager = GSVKeyManager()
