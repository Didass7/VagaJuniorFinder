import time
import logging
import schedule
from main import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Scheduler")

TARGET_TIME = "08:00"

def job_task():
    logger.info("⏰ Scheduled trigger fired! Starting daily job search...")
    try:
        run_pipeline(dry_run=False)
    except Exception as e:
        logger.error(f"❌ Error during scheduled pipeline execution: {e}")

def start_scheduler():
    logger.info(f"📅 VagaJuniorFinder Scheduler started. Configured to run daily at {TARGET_TIME}.")
    schedule.every().day.at(TARGET_TIME).do(job_task)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
