import os
import glob
import time
import subprocess
import sys
import logging
import schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Scheduler")

TARGET_TIME = "21:00"

def job_task():
    logger.info("⏰ Scheduled trigger fired! Starting daily job search for all profiles...")
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        run_all_script = os.path.join(project_root, "run_all.py")
        subprocess.run([sys.executable, run_all_script], cwd=project_root, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error during scheduled pipeline execution: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error during scheduled pipeline execution: {e}")

def start_scheduler():
    logger.info(f"📅 VagaJuniorFinder Scheduler started. Configured to run daily at {TARGET_TIME} for all profiles.")
    schedule.every().day.at(TARGET_TIME).do(job_task)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
