import os
import shutil
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class ParameterManager:
    """
    Responsibilities:
    1. Read the 'Master' TestRun/InfoFile template.
    2. Inject optimization parameters (Vector x) into the text.
    3. Generate a unique, temporary TestRun file for the simulation.
    """
    def __init__(self, template_dir: str, work_dir: str):
        self.template_dir = template_dir
        self.work_dir = work_dir

    def create_run_configuration(self, run_id: str, params: Dict[str, float], template_name: str) -> str:
        """
        Creates a new TestRun file with specific parameters.
        Returns: The name of the new TestRun file (without extension).
        """
        template_path = os.path.join(self.template_dir, template_name)
        new_run_name = f"{run_id}"
        new_run_path = os.path.join(self.work_dir, "Data", "TestRun", new_run_name) # CM standard path

        try:
            with open(template_path, 'r') as f:
                content = f.read()

            # --- The "Injection" Logic ---
            # This replaces placeholders or specific keys in the text file.
            # Strategy: Look for specific lines or use a placeholder syntax like {{stiffness_front}}
            
            for key, value in params.items():
                # Example: Replace "Spring.Front = 50000" with "Spring.Front = <new_value>"
                # A simple replacement approach (assuming you put placeholders in your template):
                # content = content.replace(f"{{{{{key}}}}}", str(value))
                
                # A robust key-value replacement approach (if no placeholders):
                # Search for "Key = Val" and replace it.
                # Here we stick to a simple placeholder logic for clarity:
                placeholder = f"<{key}>" 
                if placeholder in content:
                    content = content.replace(placeholder, str(value))
                else:
                    logger.warning(f"Parameter placeholder {placeholder} not found in template.")

            # Write the new physical file
            # Ensure the directory exists
            os.makedirs(os.path.dirname(new_run_path), exist_ok=True)
            
            with open(new_run_path, 'w') as f:
                f.write(content)
            
            logger.debug(f"Generated configuration for {run_id}")
            return new_run_name

        except Exception as e:
            logger.error(f"Failed to create run configuration: {e}")
            raise e