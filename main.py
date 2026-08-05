import argparse
import logging
import sys
import io
from config import config
from scraper import JobIngestionPipeline
from matcher import JobMatcher
from report_builder import ReportBuilder
from notifier import EmailNotifier
from telegram_notifier import TelegramNotifier
from seen_store import SeenStore

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

    # 1b. Cross-run deduplication — skip jobs we've already processed
    seen = SeenStore(filepath=config.cache_file)
    new_jobs = seen.filter_new(raw_jobs)
    logger.info(f"🧠 Seen store: {seen.count} tracked | {len(raw_jobs)} ingested | {len(new_jobs)} new")

    if not new_jobs:
        logger.info("✅ All jobs were already seen in previous runs. Nothing new to report.")
        seen.save()
        return

    # 2. Matching & Scoring
    matcher = JobMatcher(profile=config.candidate)
    scored_jobs = matcher.process_jobs(new_jobs)
    logger.info(f"✅ Evaluated {len(scored_jobs)} jobs relevant for matching score evaluation.")

    # Mark all new jobs as seen (even low-scored ones, to avoid re-processing)
    seen.mark_seen([j.job_id for j in new_jobs])
    seen.save()

    # 3. Report Building
    report_builder = ReportBuilder(profile=config.candidate)
    markdown_content = report_builder.build_markdown(scored_jobs)
    telegram_html_content = report_builder.build_telegram_html(scored_jobs)
    
    saved_report_path = report_builder.save_report(markdown_content, output_dir=config.reports_dir)
    logger.info(f"📄 Markdown report saved to: {saved_report_path}")

    # 4. Dispatch Notifications
    if dry_run:
        logger.info("ℹ️ Dry-run mode active. Skipping notification dispatch.")
        logger.info("---------------- REPORT PREVIEW ----------------")
        try:
            print(markdown_content[:800] + "\n\n[... truncated preview ...]")
        except Exception:
            print(markdown_content[:800].encode('ascii', errors='replace').decode('ascii') + "\n\n[... truncated preview ...]")
        logger.info("------------------------------------------------")
    else:
        # A) Telegram Notification (Primary)
        if config.telegram_bot_token and config.telegram_chat_id:
            telegram_bot = TelegramNotifier(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id
            )
            telegram_bot.send_message(telegram_html_content, parse_mode="HTML")
            telegram_bot.send_document(saved_report_path, caption="📄 Relatório completo em Markdown")
        else:
            logger.info("ℹ️ Telegram credentials not configured. Skipping Telegram dispatch.")

        # B) Email Notification (Secondary)
        if config.smtp_password:
            notifier = EmailNotifier(
                smtp_server=config.smtp_server,
                smtp_port=config.smtp_port,
                smtp_email=config.smtp_email,
                smtp_password=config.smtp_password,
                receiver_email=config.receiver_email
            )
            notifier.send_email_report(markdown_content, md_filepath=saved_report_path)
        else:
            logger.info("ℹ️ Email SMTP password not configured. Skipping Email dispatch.")

    logger.info("==================================================")
    logger.info("✅ VagaJuniorFinder Pipeline Finished Successfully")
    logger.info("==================================================")

def main():
    parser = argparse.ArgumentParser(description="VagaJuniorFinder — Daily Junior AI & Data Science Job Finder")
    parser.add_argument("--dry-run", action="store_true", help="Run ingestion and report generation without sending notifications")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose log level")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_pipeline(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
