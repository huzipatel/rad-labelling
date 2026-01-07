"""Spreadsheet parsing service."""
import io
from typing import List, Dict, Any
import pandas as pd


class SpreadsheetParser:
    """Parse uploaded spreadsheets (Excel/CSV) into location data."""
    
    def parse(
        self,
        file_contents: bytes,
        filename: str,
        lat_column: str = "Latitude",
        lng_column: str = "Longitude",
        identifier_column: str = "ATCOCode"
    ) -> List[Dict[str, Any]]:
        """
        Parse spreadsheet contents into location records.
        
        Args:
            file_contents: Raw file bytes
            filename: Original filename for determining format
            lat_column: Name of latitude column
            lng_column: Name of longitude column
            identifier_column: Name of identifier column
        
        Returns:
            List of location dictionaries
        """
        # Determine file type and read accordingly
        ext = filename.split(".")[-1].lower()
        
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(file_contents))
        elif ext in ["xlsx", "xls"]:
            df = pd.read_excel(io.BytesIO(file_contents))
        else:
            raise ValueError(f"Unsupported file format: {ext}")
        
        # Validate required columns
        required_columns = [lat_column, lng_column, identifier_column]
        missing = [col for col in required_columns if col not in df.columns]
        
        if missing:
            # Try case-insensitive match
            df.columns = df.columns.str.strip()
            column_map = {col.lower(): col for col in df.columns}
            
            for i, col in enumerate(required_columns):
                if col.lower() in column_map:
                    required_columns[i] = column_map[col.lower()]
            
            lat_column, lng_column, identifier_column = required_columns
            
            missing = [col for col in [lat_column, lng_column, identifier_column] 
                      if col not in df.columns]
            
            if missing:
                raise ValueError(f"Missing required columns: {', '.join(missing)}")
        
        # Parse locations
        locations = []
        
        for idx, row in df.iterrows():
            try:
                lat = float(row[lat_column])
                lng = float(row[lng_column])
                identifier = str(row[identifier_column]).strip()
                
                if not identifier:
                    continue
                
                # Validate coordinates
                if not (-90 <= lat <= 90):
                    print(f"Invalid latitude at row {idx}: {lat}")
                    continue
                
                if not (-180 <= lng <= 180):
                    print(f"Invalid longitude at row {idx}: {lng}")
                    continue
                
                # Store original row data
                original_data = row.to_dict()
                # Convert any non-JSON-serializable values
                for key, value in original_data.items():
                    if pd.isna(value):
                        original_data[key] = None
                    elif hasattr(value, 'isoformat'):
                        original_data[key] = value.isoformat()
                
                locations.append({
                    "identifier": identifier,
                    "latitude": lat,
                    "longitude": lng,
                    "original_data": original_data
                })
                
            except (ValueError, TypeError) as e:
                print(f"Error parsing row {idx}: {e}")
                continue
        
        if not locations:
            raise ValueError("No valid locations found in spreadsheet")
        
        return locations
    
    def get_column_names(self, file_contents: bytes, filename: str) -> List[str]:
        """Get column names from a spreadsheet."""
        ext = filename.split(".")[-1].lower()
        
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(file_contents), nrows=0)
        elif ext in ["xlsx", "xls"]:
            df = pd.read_excel(io.BytesIO(file_contents), nrows=0)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
        
        return list(df.columns)

