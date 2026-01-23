"""
GSV API Key Manager with rate limiting and automatic failover.

Manages multiple Google Street View API keys, automatically rotating
between them and handling rate limits (403 errors).
"""
import asyncio
import time
from datetime import datetime, date
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from threading import Lock

from app.core.config import settings


@dataclass
class KeyStats:
    """Statistics for a single API key."""
    key: str
    requests_today: int = 0
    requests_this_minute: int = 0
    last_request_time: float = 0
    last_403_time: Optional[float] = None
    is_rate_limited: bool = False
    daily_limit_reached: bool = False
    last_reset_date: date = field(default_factory=date.today)
    consecutive_403s: int = 0
    
    def reset_if_new_day(self):
        """Reset daily counters if it's a new day."""
        today = date.today()
        if self.last_reset_date != today:
            self.requests_today = 0
            self.daily_limit_reached = False
            self.is_rate_limited = False
            self.consecutive_403s = 0
            self.last_reset_date = today
            print(f"[GSV KeyManager] Reset daily counters for key {self.key[:8]}...")
    
    def reset_minute_counter_if_needed(self):
        """Reset per-minute counter if more than 60 seconds have passed."""
        now = time.time()
        if now - self.last_request_time > 60:
            self.requests_this_minute = 0


class GSVKeyManager:
    """
    Manages multiple GSV API keys with automatic rotation and failover.
    
    Features:
    - Round-robin key rotation
    - Per-minute rate limiting (respects Google's 30,000/min limit)
    - Daily limit tracking (25,000/day per key)
    - Automatic failover on 403 errors
    - Thread-safe for concurrent access
    """
    
    _instance: Optional['GSVKeyManager'] = None
    _lock = Lock()
    
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
        self._keys: Dict[str, KeyStats] = {}
        self._current_key_index = 0
        self._request_lock = asyncio.Lock()
        self._sync_lock = Lock()
        
        # Initialize keys from settings
        api_keys = settings.gsv_api_keys_list
        if not api_keys:
            print("[GSV KeyManager] WARNING: No API keys configured!")
        else:
            for key in api_keys:
                self._keys[key] = KeyStats(key=key)
            print(f"[GSV KeyManager] Initialized with {len(self._keys)} API key(s)")
    
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
            if not stats.daily_limit_reached and not stats.is_rate_limited:
                count += 1
        return count
    
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
                "key_prefix": key[:8] + "...",
                "requests_today": stats.requests_today,
                "daily_limit_reached": stats.daily_limit_reached,
                "is_rate_limited": stats.is_rate_limited,
                "consecutive_403s": stats.consecutive_403s
            })
        
        return status
    
    async def get_key(self) -> Optional[str]:
        """
        Get the next available API key using round-robin with failover.
        
        Returns None if all keys are exhausted.
        """
        if not self._keys:
            return None
        
        async with self._request_lock:
            keys_list = list(self._keys.keys())
            attempts = 0
            
            while attempts < len(keys_list):
                # Round-robin selection
                key = keys_list[self._current_key_index % len(keys_list)]
                self._current_key_index = (self._current_key_index + 1) % len(keys_list)
                
                stats = self._keys[key]
                stats.reset_if_new_day()
                stats.reset_minute_counter_if_needed()
                
                # Check if key is usable
                if stats.daily_limit_reached:
                    attempts += 1
                    continue
                
                if stats.is_rate_limited:
                    # Check if enough time has passed (wait at least 60s after rate limit)
                    if stats.last_403_time and time.time() - stats.last_403_time < 60:
                        attempts += 1
                        continue
                    else:
                        stats.is_rate_limited = False
                
                # Check per-minute rate limit
                if stats.requests_this_minute >= settings.GSV_REQUESTS_PER_MINUTE:
                    # Wait until minute resets
                    wait_time = 60 - (time.time() - stats.last_request_time)
                    if wait_time > 0:
                        attempts += 1
                        continue
                    else:
                        stats.requests_this_minute = 0
                
                return key
            
            # All keys exhausted
            print("[GSV KeyManager] All API keys are exhausted or rate-limited!")
            return None
    
    async def record_request(self, key: str, success: bool = True, status_code: int = 200):
        """
        Record a request result for tracking.
        
        Args:
            key: The API key used
            success: Whether the request was successful
            status_code: HTTP status code from the response
        """
        if key not in self._keys:
            return
        
        async with self._request_lock:
            stats = self._keys[key]
            stats.requests_today += 1
            stats.requests_this_minute += 1
            stats.last_request_time = time.time()
            
            if status_code == 403:
                stats.consecutive_403s += 1
                stats.last_403_time = time.time()
                
                # After 5 consecutive 403s, assume daily limit reached
                if stats.consecutive_403s >= 5:
                    stats.daily_limit_reached = True
                    print(f"[GSV KeyManager] Key {key[:8]}... marked as daily limit reached after {stats.consecutive_403s} consecutive 403s")
                else:
                    stats.is_rate_limited = True
                    print(f"[GSV KeyManager] Key {key[:8]}... temporarily rate limited (403 #{stats.consecutive_403s})")
            
            elif status_code == 200:
                # Reset consecutive 403 counter on success
                stats.consecutive_403s = 0
                
                # Check if approaching daily limit
                if stats.requests_today >= settings.GSV_DAILY_LIMIT_PER_KEY:
                    stats.daily_limit_reached = True
                    print(f"[GSV KeyManager] Key {key[:8]}... reached daily limit of {settings.GSV_DAILY_LIMIT_PER_KEY}")
    
    async def throttle(self):
        """
        Apply minimal delay between requests.
        
        With multiple keys, we can be very aggressive.
        Google allows 30,000 requests/min per key.
        """
        # Minimal delay - just enough to not hammer the API
        delay = settings.GSV_MIN_DELAY_MS / 1000.0  # Convert ms to seconds
        if delay > 0:
            await asyncio.sleep(delay)
    
    def force_reset_key(self, key_prefix: str):
        """Force reset a key's rate limit status (admin function)."""
        for key, stats in self._keys.items():
            if key.startswith(key_prefix):
                stats.is_rate_limited = False
                stats.daily_limit_reached = False
                stats.consecutive_403s = 0
                print(f"[GSV KeyManager] Force reset key {key[:8]}...")
                return True
        return False
    
    def reload_keys(self):
        """Reload API keys from settings (useful after config changes)."""
        with self._sync_lock:
            api_keys = settings.gsv_api_keys_list
            
            # Add new keys
            for key in api_keys:
                if key not in self._keys:
                    self._keys[key] = KeyStats(key=key)
                    print(f"[GSV KeyManager] Added new key {key[:8]}...")
            
            # Remove keys that are no longer in config
            keys_to_remove = [k for k in self._keys if k not in api_keys]
            for key in keys_to_remove:
                del self._keys[key]
                print(f"[GSV KeyManager] Removed key {key[:8]}...")
            
            print(f"[GSV KeyManager] Now managing {len(self._keys)} key(s)")


# Global instance
gsv_key_manager = GSVKeyManager()

