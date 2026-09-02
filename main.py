import argparse
import logging
import sys
import io
from typing import Optional
from core.config import config
from scrapers import JobIngestionPipeline
from core.matcher import JobMatcher
from core.seen_store import SeenStore
from integrations.notion_store import NotionStore

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

def run_pipeline(
    dry_run: bool = False,
    pipeline: Optional[JobIngestionPipeline] = None,
    seen_store: Optional[SeenStore] = None,
    matcher: Optional[JobMatcher] = None,
    notion_store: Optional[NotionStore] = None
):
    logger.info("==================================================")
    logger.info("🚀 VagaJuniorFinder Pipeline Started")
    logger.info(f"Target Candidate: {config.candidate.name} ({config.candidate.email})")
    logger.info("==================================================")

    # ── Step 1: Scrape ── Fetch jobs from all portals (with early SeenStore check)
    seen = seen_store if seen_store is not None else SeenStore(filepath=config.cache_file)
    pipe = pipeline if pipeline is not None else JobIngestionPipeline(
        itjobs_api_key=config.itjobs_api_key,
        seen_store=seen,
        search_queries=config.candidate.search_queries
    )
    raw_jobs = pipe.run()

    if not raw_jobs:
        logger.warning("⚠️ No jobs found across any sources today.")
        return

    # ── Step 2: Deduplicate ── Keep only jobs we haven't seen before
    new_jobs = seen.filter_new(raw_jobs)

    logger.info(f"🧠 Seen store: {seen.count} tracked | {len(raw_jobs)} ingested | {len(new_jobs)} new")

    if not new_jobs:
        logger.info("ℹ️ No new jobs found today. All ingested jobs were already seen.")
        return

    # ── Step 3: Filter & Score ── Heuristic pre-filter + AI evaluation
    match_engine = matcher if matcher is not None else JobMatcher(profile=config.candidate)
    scored_jobs = match_engine.process_jobs(new_jobs)

    logger.info(f"✅ Evaluated: {len(scored_jobs)} qualified jobs out of {len(new_jobs)} new jobs.")

    if dry_run:
        logger.info("ℹ️ Dry-run mode active. Skipping Notion sync and seen-store update.")
        for sj in scored_jobs[:10]:
            logger.info(f"  → [{sj.score}%] {sj.job.title} @ {sj.job.company} ({sj.seniority_status})")
    else:
        jobs_to_mark = []
        try:
            # ── Step 4: Sync to Notion ── Send qualified new jobs to Notion database
            if config.enable_notion_sync:
                notion = notion_store if notion_store is not None else NotionStore()
                successful_job_ids = notion.sync_jobs(scored_jobs, threshold=config.promising_match_threshold)
                synced_new = getattr(notion, 'last_synced_count', len(successful_job_ids))
                already_in_db = max(0, len(successful_job_ids) - synced_new)
                logger.info(f"📝 Synced {synced_new} brand-new jobs to Notion ({already_in_db} were already in Notion database).")
            else:
                logger.info("ℹ️ Notion sync disabled.")
                successful_job_ids = {sj.job.job_id for sj in scored_jobs}

            # Mark as seen ONLY jobs that were filtered out OR successfully synced
            scored_job_ids = {sj.job.job_id for sj in scored_jobs}
            jobs_to_mark = [j.job_id for j in new_jobs if j.job_id not in scored_job_ids or j.job_id in successful_job_ids]
        except Exception as e:
            logger.error(f"❌ Error during Notion sync: {e}")
            # On sync failure, still mark disqualified jobs as seen to avoid re-processing
            scored_job_ids = {sj.job.job_id for sj in scored_jobs}
            jobs_to_mark = [j.job_id for j in new_jobs if j.job_id not in scored_job_ids]
        finally:
            seen.mark_seen(jobs_to_mark)
            seen.save()

    logger.info("==================================================")
    logger.info("✅ VagaJuniorFinder Pipeline Finished Successfully")
    logger.info("==================================================")

def main():
    parser = argparse.ArgumentParser(description="VagaJuniorFinder — Daily Junior AI & Data Science Job Finder")
    parser.add_argument("--dry-run", action="store_true", help="Run ingestion and scoring without syncing to Notion")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose log level")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_pipeline(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
