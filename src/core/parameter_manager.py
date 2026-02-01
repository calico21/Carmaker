import os
import shutil
import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)

class ParameterManager:
    """
    GEN 6.0: FULL PARAMETER CONTROL.
    Handles TestRun files AND Vehicle Geometry files.
    """
    def __init__(self, template_dir: str, work_dir: str):
        self.template_dir = template_dir
        self.work_dir = work_dir

    def inject_hardpoints(self, vehicle_file_path: str, hardpoints: Dict[str, float]):
        """
        DIRECTLY MODIFIES SUSPENSION GEOMETRY.
        Reads the Vehicle Dataset, finds the Hardpoint coordinates, and updates them.
        This enables 'Kinematic Optimization'.
        """
        try:
            with open(vehicle_file_path, 'r') as f:
                lines = f.readlines()
            
            new_lines = []
            modified_count = 0
            
            for line in lines:
                # Line format example: "Hardpoint.FL.Wishbone.Upper.Z = 0.285"
                line_modified = False
                for hp_key, hp_val in hardpoints.items():
                    # Check if this line defines the hardpoint we want to change
                    if hp_key in line and "=" in line:
                        # Split by '=', keep the key, update the value
                        key_part, _ = line.split("=")
                        new_lines.append(f"{key_part}= {hp_val}\n")
                        line_modified = True
                        modified_count += 1
                        break
                
                if not line_modified:
                    new_lines.append(line)
            
            # Write back the modified vehicle file
            with open(vehicle_file_path, 'w') as f:
                f.writelines(new_lines)
                
            logger.debug(f"Injected {modified_count} hardpoints into {os.path.basename(vehicle_file_path)}")
            
        except Exception as e:
            logger.error(f"Failed to inject hardpoints: {e}")

    def create_run_configuration(self, run_id: str, params: Dict[str, float], template_name: str) -> str:
        """
        Creates a new TestRun file with updated Spring/Damper settings.
        """
        template_path = os.path.join(self.template_dir, template_name)
        new_run_name = f"{run_id}"
        new_run_path = os.path.join(self.work_dir, "Data", "TestRun", new_run_name)

        try:
            with open(template_path, 'r') as f:
                content = f.read()

            for key, value in params.items():
                # Ignore geometry params (HP_...) since those go to the Vehicle file, not TestRun
                if not key.startswith("HP_"):
                    # Regex replacement for "Spring.Front = 50000"
                    pattern = rf"({re.escape(key)}\s*=\s*)([\d\.\-eE]+)"
                    if re.search(pattern, content):
                        content = re.sub(pattern, f"\\g<1>{value}", content)
            
            os.makedirs(os.path.dirname(new_run_path), exist_ok=True)
            with open(new_run_path, 'w') as f:
                f.write(content)
                
            return new_run_name

        except Exception as e:
            logger.error(f"Failed to create TestRun: {e}")
            raise e