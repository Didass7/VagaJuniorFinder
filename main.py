import argparse
import logging
import sys
import io
from config import config
from scraper import JobIngestionPipeline
from matcher import JobMatcher
from report_builder import ReportBuilder
from notifier import EmailNotifier

# Ensure Windows terminal stdout handles UTF-8 emojis cleanly
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VagaJuniorFinder")

def run_pipeline(dry_run: bool = False):
    logger.info("==================================================")
    logger.info("🚀 VagaJuniorFinder Pipeline Started")
    logger.info(f"Target Candidate: {config.candidate.name} ({config.candidate.email})")
    logger.info("==================================================")

    # 1. Ingestion & Deduplication
    pipeline = JobIngestionPipeline(itjobs_api_key=config.itjobs_api_key)
    raw_jobs = pipeline.run()

    if not raw_jobs:
        logger.warning("⚠️ No jobs found across any sources today.")
        return

    # 2. Matching & Scoring
    matcher = JobMatcher(profile=config.candidate)
    scored_jobs = matcher.process_jobs(raw_jobs)
    logger.info(f"✅ Evaluated {len(scored_jobs)} jobs relevant for matching score evaluation.")

    # 3. Report Building
    report_builder = ReportBuilder(profile=config.candidate)
    markdown_content = report_builder.build_markdown(scored_jobs)
    saved_report_path = report_builder.save_report(markdown_content, output_dir=config.reports_dir)
    logger.info(f"📄 Markdown report saved to: {saved_report_path}")

    # 4. Email Notification
    if dry_run:
        logger.info("ℹ️ Dry-run mode active. Skipping email dispatch.")
        logger.info("---------------- REPORT PREVIEW ----------------")
        try:
            print(markdown_content[:800] + "\n\n[... truncated preview ...]")
        except Exception:
            print(markdown_content[:800].encode('ascii', errors='replace').decode('ascii') + "\n\n[... truncated preview ...]")
        logger.info("------------------------------------------------")
    else:
        notifier = EmailNotifier(
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            smtp_email=config.smtp_email,
            smtp_password=config.smtp_password,
            receiver_email=config.receiver_email
        )
        notifier.send_email_report(markdown_content, md_filepath=saved_report_path)

    logger.info("==================================================")
    logger.info("✅ VagaJuniorFinder Pipeline Finished Successfully")
    logger.info("==================================================")

def main():
    parser = argparse.ArgumentParser(description="VagaJuniorFinder — Daily Junior AI & Data Science Job Finder")
    parser.add_argument("--dry-run", action="store_true", help="Run ingestion and report generation without sending email")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose log level")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_pipeline(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
