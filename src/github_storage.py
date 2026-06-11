"""
github_storage.py
=================
Handles bidirectional data synchronization between Hugging Face Spaces 
and a GitHub repository. This allows persistent storage of databases, 
notes, and configuration files on GitHub, bypassing HF Space's 
ephemeral storage limitations.
"""

import os
import shutil
import subprocess
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class GitHubStorage:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("GITHUB_REPO") # format: username/repo
        self.branch = os.getenv("GITHUB_STORAGE_BRANCH", "data-storage")
        self.data_dir = Path("./data")
        self.sync_interval = int(os.getenv("SYNC_INTERVAL_MINUTES", "30"))
        
        if self.token and self.repo:
            self.remote_url = f"https://{self.token}@github.com/{self.repo}.git"
        else:
            self.remote_url = None

    def _run_git(self, args, cwd=None):
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"Git error: {e.stderr}")
            return None

    def initialize_storage(self):
        """Initialize the data-storage branch if it doesn't exist."""
        if not self.remote_url:
            logger.warning("GITHUB_TOKEN or GITHUB_REPO not set. Storage sync disabled.")
            return False

        logger.info(f"Initializing GitHub storage on branch {self.branch}...")
        
        # Create a temp dir for sync
        sync_dir = Path("/tmp/odysseus_sync")
        if sync_dir.exists():
            shutil.rmtree(sync_dir)
        sync_dir.mkdir(parents=True)

        self._run_git(["init"], cwd=sync_dir)
        self._run_git(["remote", "add", "origin", self.remote_url], cwd=sync_dir)
        
        # Try to pull existing data
        try:
            self._run_git(["fetch", "origin", self.branch], cwd=sync_dir)
            self._run_git(["checkout", self.branch], cwd=sync_dir)
            logger.info("Existing data storage branch found and pulled.")
            
            # Copy pulled data to local data dir
            if os.path.exists(sync_dir):
                for item in os.listdir(sync_dir):
                    if item != ".git":
                        src = sync_dir / item
                        dst = self.data_dir / item
                        if src.is_dir():
                            if dst.exists(): shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
            return True
        except:
            logger.info("Creating new data storage branch...")
            self._run_git(["checkout", "-b", self.branch], cwd=sync_dir)
            with open(sync_dir / ".keep", "w") as f: f.write("")
            self._run_git(["add", "."], cwd=sync_dir)
            self._run_git(["commit", "-m", "chore: initialize data storage"], cwd=sync_dir)
            self._run_git(["push", "-u", "origin", self.branch], cwd=sync_dir)
            return True

    def sync_to_github(self):
        """Push local data changes to GitHub."""
        if not self.remote_url: return
        
        logger.info("Syncing data to GitHub...")
        sync_dir = Path("/tmp/odysseus_sync")
        
        # Ensure sync dir is ready
        if not (sync_dir / ".git").exists():
            self.initialize_storage()

        # Copy local data to sync dir
        for item in os.listdir(self.data_dir):
            src = self.data_dir / item
            dst = sync_dir / item
            if src.is_dir():
                if dst.exists(): shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # Commit and push
        self._run_git(["add", "."], cwd=sync_dir)
        status = self._run_git(["status", "--porcelain"], cwd=sync_dir)
        if status and status.strip():
            self._run_git(["commit", "-m", f"data: sync at {time.strftime('%Y-%m-%d %H:%M:%S')}"], cwd=sync_dir)
            self._run_git(["push", "origin", self.branch], cwd=sync_dir)
            logger.info("Data pushed to GitHub successfully.")
        else:
            logger.info("No data changes to push.")

def start_sync_thread():
    """Start a background thread to sync data periodically."""
    import threading
    storage = GitHubStorage()
    storage.initialize_storage()
    
    def run_forever():
        while True:
            try:
                time.sleep(storage.sync_interval * 60)
                storage.sync_to_github()
            except Exception as e:
                logger.error(f"Sync thread error: {e}")
                time.sleep(60)

    thread = threading.Thread(target=run_forever, daemon=True)
    thread.start()
    return storage
