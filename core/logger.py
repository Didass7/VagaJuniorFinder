import logging
import sys
import io

def setup_logging(level=logging.INFO):
    """Standardizes logging configuration across the entire VagaJuniorFinder project."""
    
    # Ensure Windows terminal stdout handles UTF-8 emojis cleanly
    if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True
    )
    
    # Silence chatty third-party dependencies
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("WDM").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)

# Auto-initialize with defaults when imported
setup_logging()
