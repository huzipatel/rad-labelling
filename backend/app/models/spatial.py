"""Spatial models for council boundaries, roads, etc."""
from typing import Any
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geography

from app.core.database import Base


class CouncilBoundary(Base):
    """Council boundary spatial model."""
    
    __tablename__ = "council_boundaries"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    council_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    council_code: Mapped[str] = mapped_column(String(50), nullable=True)
    boundary: Mapped[Any] = mapped_column(
        Geography(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<CouncilBoundary {self.council_name}>"


class CombinedAuthority(Base):
    """Combined authority spatial model."""
    
    __tablename__ = "combined_authorities"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    authority_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    authority_code: Mapped[str] = mapped_column(String(50), nullable=True)
    boundary: Mapped[Any] = mapped_column(
        Geography(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<CombinedAuthority {self.authority_name}>"


class RoadClassification(Base):
    """Road classification spatial model."""
    
    __tablename__ = "road_classifications"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    road_name: Mapped[str] = mapped_column(String(255), nullable=True)
    road_class: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    road_number: Mapped[str] = mapped_column(String(20), nullable=True)
    geometry: Mapped[Any] = mapped_column(
        Geography(geometry_type="MULTILINESTRING", srid=4326),
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<RoadClassification {self.road_class}>"

