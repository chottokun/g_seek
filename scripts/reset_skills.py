#!/usr/bin/env python3
import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_skills():
    target_dir = os.path.join(os.path.dirname(__file__), "data", "skills")
    backup_dir = os.path.join(os.path.dirname(__file__), "data", "skills_backup")
    
    if os.path.exists(target_dir):
        logger.info(f"Clearing current skills directory: {target_dir}")
        shutil.rmtree(target_dir)
        
    if os.path.exists(backup_dir):
        logger.info(f"Restoring from backup: {backup_dir}")
        shutil.copytree(backup_dir, target_dir)
        logger.info("Skills successfully reset to initial state.")
    else:
        logger.error("Backup directory not found. Cannot reset.")

if __name__ == "__main__":
    reset_skills()
