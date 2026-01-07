"""Spatial enhancement service using PostGIS."""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class SpatialEnhancer:
    """Enhance location data with spatial lookups."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def enhance_location(
        self,
        latitude: float,
        longitude: float,
        enhance_council: bool = True,
        enhance_road: bool = True,
        enhance_authority: bool = True
    ) -> Dict[str, Any]:
        """
        Enhance a location with council, road classification, and combined authority.
        
        Args:
            latitude: Location latitude
            longitude: Location longitude
            enhance_council: Whether to look up council boundary
            enhance_road: Whether to look up road classification
            enhance_authority: Whether to look up combined authority
        
        Returns:
            Dictionary with enhanced data
        """
        result = {
            "council": None,
            "road_classification": None,
            "combined_authority": None
        }
        
        point = f"POINT({longitude} {latitude})"
        
        if enhance_council:
            result["council"] = await self._find_council(point)
        
        if enhance_road:
            result["road_classification"] = await self._find_road_classification(point)
        
        if enhance_authority:
            result["combined_authority"] = await self._find_combined_authority(point)
        
        return result
    
    async def _find_council(self, point: str) -> Optional[str]:
        """Find council for a point using ST_Contains."""
        query = text("""
            SELECT council_name 
            FROM council_boundaries 
            WHERE ST_Contains(
                boundary::geometry, 
                ST_GeomFromText(:point, 4326)
            )
            LIMIT 1
        """)
        
        result = await self.db.execute(query, {"point": point})
        row = result.fetchone()
        
        return row[0] if row else None
    
    async def _find_road_classification(self, point: str) -> Optional[str]:
        """Find nearest road classification within 50 meters."""
        query = text("""
            SELECT road_class 
            FROM road_classifications 
            WHERE ST_DWithin(
                geometry::geography, 
                ST_GeomFromText(:point, 4326)::geography, 
                50
            )
            ORDER BY ST_Distance(
                geometry::geography, 
                ST_GeomFromText(:point, 4326)::geography
            )
            LIMIT 1
        """)
        
        result = await self.db.execute(query, {"point": point})
        row = result.fetchone()
        
        return row[0] if row else None
    
    async def _find_combined_authority(self, point: str) -> Optional[str]:
        """Find combined authority for a point (if any)."""
        query = text("""
            SELECT authority_name 
            FROM combined_authorities 
            WHERE ST_Contains(
                boundary::geometry, 
                ST_GeomFromText(:point, 4326)
            )
            LIMIT 1
        """)
        
        result = await self.db.execute(query, {"point": point})
        row = result.fetchone()
        
        return row[0] if row else None
    
    async def bulk_enhance(
        self,
        locations: list,
        enhance_council: bool = True,
        enhance_road: bool = True,
        enhance_authority: bool = True
    ) -> list:
        """
        Enhance multiple locations efficiently.
        
        For large datasets, this could be optimized to use
        batch spatial queries.
        """
        enhanced = []
        
        for loc in locations:
            data = await self.enhance_location(
                loc["latitude"],
                loc["longitude"],
                enhance_council,
                enhance_road,
                enhance_authority
            )
            enhanced.append({**loc, **data})
        
        return enhanced

