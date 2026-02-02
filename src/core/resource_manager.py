import os
import datetime
import shutil
import logging

class ResourceManager:
    """
    The Librarian.
    Responsibility: Manages the file system to ensure every simulation 
    has a clean, isolated environment.
    
    Structure:
    Output/
      └── Campaign_YYYY-MM-DD_HH-MM/
          ├── optimization.db
          ├── Trial_000/
          ├── Trial_001/
          └── ...
    """
    def __init__(self, base_dir="Output"):
        self.logger = logging.getLogger("ResourceManager")
        self.base_dir = base_dir
        
        # Create a unique name for this entire optimization session
        # Format: Output/Campaign_YYYY-MM-DD_HH-MM
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.campaign_folder = os.path.join(self.base_dir, f"Campaign_{timestamp}")
        
        # Create the main folder immediately
        try:
            os.makedirs(self.campaign_folder, exist_ok=True)
            self.logger.info(f"📂 Created Campaign Folder: {self.campaign_folder}")
            print(f"📂 Created Campaign Folder: {self.campaign_folder}")
        except OSError as e:
            self.logger.error(f"Failed to create campaign folder: {e}")
            raise

    def setup_trial_folder(self, trial_number):
        """
        Creates a sub-folder for a specific run (e.g., Trial_042).
        Returns the absolute path so other scripts know where to save files.
        """
        trial_name = f"Trial_{trial_number:03d}"
        path = os.path.join(self.campaign_folder, trial_name)
        
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError as e:
            self.logger.error(f"Failed to create trial folder {path}: {e}")
            return None

    def get_db_path(self):
        """
        Returns the SQLalchemy connection string for the database.
        We place the DB inside the campaign folder so it's portable.
        """
        # SQLite needs 3 slashes for relative path, 4 for absolute.
        # We use absolute path to be safe.
        db_file_path = os.path.join(self.campaign_folder, 'optimization.db')
        abs_path = os.path.abspath(db_file_path)
        
        # Windows compatibility check for path separators
        if os.name == 'nt':
            abs_path = abs_path.replace('\\', '/')
            
        return f"sqlite:///{abs_path}"

    def get_campaign_path(self):
        """Returns the root path of the current campaign."""
        return self.campaign_folder