"""
CSV Loader Module
Handles loading and parsing CSV files into memory.
"""

import pandas as pd
from pathlib import Path


class CSVLoader:
    """Load and manage CSV files in memory."""
    
    def __init__(self, file_path: str):
        """
        Initialize the CSV loader with a file path.
        
        Args:
            file_path: Path to the CSV file
            
        Raises:
            FileNotFoundError: If the file does not exist
            ValueError: If the file is not a CSV file
        """
        self.file_path = Path(file_path)
        self._validate_file()
        self.data = None
    
    def _validate_file(self):
        """Validate that the file exists and is a CSV file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        if self.file_path.suffix.lower() != '.csv':
            raise ValueError(f"File must be a CSV file, got: {self.file_path.suffix}")
    
    def load(self, encoding='utf-8'):
        """
        Load the CSV file into memory.
        
        Args:
            encoding: File encoding (default: 'utf-8')
            
        Returns:
            pandas.DataFrame: The loaded CSV data
            
        Raises:
            Exception: If CSV parsing fails
        """
        try:
            self.data = pd.read_csv(self.file_path, encoding=encoding)
            return self.data
        except UnicodeDecodeError:
            # Try with latin-1 encoding as fallback
            self.data = pd.read_csv(self.file_path, encoding='latin-1')
            return self.data
        except Exception as e:
            raise Exception(f"Failed to parse CSV file: {str(e)}")
    
    def get_data(self):
        """
        Get the loaded data.
        
        Returns:
            pandas.DataFrame: The loaded CSV data, or None if not loaded
        """
        if self.data is None:
            raise RuntimeError("No data loaded. Call load() first.")
        return self.data
    
    def reload(self):
        """Reload the CSV file."""
        self.data = None
        return self.load()
