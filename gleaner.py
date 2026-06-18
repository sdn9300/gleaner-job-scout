import argparse
import sys
import logging
import os
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import adapters
from boards.naukri import NaukriAdapter
from boards.remoteok import RemoteOKAdapter
from boards.wellfound import WellfoundAdapter
from boards.indeed import IndeedAdapter

# Import filters & writers
from filters import dedupe, filter_by_role, filter_by_location
from writers import write_csv, write_to_sheet

def setup_logging(config_path="config.yaml"):
    """Configures application-wide logging using config.yaml parameters."""
    level = logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)
                if cfg and "logging" in cfg:
                    log_cfg = cfg["logging"]
                    lvl_str = log_cfg.get("level", "INFO").upper()
                    level = getattr(logging, lvl_str, logging.INFO)
                    log_format = log_cfg.get("format", log_format)
        except Exception:
            pass

    logging.basicConfig(level=level, format=log_format)

def parse_args():
    parser = argparse.ArgumentParser(description="Gleaner: Multi-Board Job Scraper CLI")
    parser.add_argument("--role", required=True, help="Job role to search for (e.g. 'data scientist')")
    parser.add_argument("--location", required=True, help="Location to search in (e.g. 'Bangalore')")
    parser.add_argument("--limit", type=int, help="Max rows in final output (post-dedupe)")
    parser.add_argument("--output", default="jobs.csv", help="Local CSV file path to output results")
    parser.add_argument("--sheet", help="Google Sheet URL to populate")
    parser.add_argument("--boards", default="all", help="Comma-separated list of boards to run (naukri,remoteok,wellfound,indeed)")
    return parser.parse_args()

def main():
    setup_logging()
    logger = logging.getLogger("gleaner")
    args = parse_args()
    
    logger.info("Initializing search: role='%s', location='%s'", args.role, args.location)
    
    # Load config defaults
    default_boards = ["naukri", "remoteok", "wellfound", "indeed"]
    max_limit = 100
    if os.path.exists("config.yaml"):
        try:
            with open("config.yaml", "r") as f:
                cfg = yaml.safe_load(f)
                if cfg:
                    default_boards = cfg.get("boards", default_boards)
                    max_limit = cfg.get("limits", {}).get("default", max_limit)
        except Exception as exc:
            logger.warning("Failed to load config.yaml: %s. Using default parameters.", exc)
            
    # Apply limit rule
    limit = args.limit if args.limit is not None else max_limit
    
    # Select boards to crawl
    if args.boards.lower() == "all":
        target_boards = default_boards
    else:
        target_boards = [b.strip().lower() for b in args.boards.split(",") if b.strip()]

    # Map names to adapter constructors
    adapter_map = {
        "naukri": NaukriAdapter,
        "remoteok": RemoteOKAdapter,
        "wellfound": WellfoundAdapter,
        "indeed": IndeedAdapter
    }
    
    raw_jobs = []
    for board_name in target_boards:
        if board_name not in adapter_map:
            logger.warning("Unknown board name '%s'. Skipping.", board_name)
            continue
            
        logger.info("Running scraper for board: '%s'", board_name)
        try:
            adapter_class = adapter_map[board_name]
            adapter = adapter_class()
            jobs = adapter.fetch(args.role, args.location)
            logger.info("Fetched %d listings from '%s'", len(jobs), board_name)
            raw_jobs.extend(jobs)
        except Exception as exc:
            logger.error("Error running board '%s': %s", board_name, exc, exc_info=True)

    logger.info("Total raw jobs collected across all boards: %d", len(raw_jobs))
    
    # Run pipeline filtering operations
    deduped_jobs = dedupe(raw_jobs)
    logger.info("Jobs after deduplication: %d", len(deduped_jobs))
    
    role_filtered = filter_by_role(deduped_jobs, args.role)
    logger.info("Jobs after role filter matching '%s': %d", args.role, len(role_filtered))
    
    loc_filtered = filter_by_location(role_filtered, args.location)
    logger.info("Jobs after location filter matching '%s': %d", args.location, len(loc_filtered))
    
    # Apply output limit
    final_jobs = loc_filtered[:limit]
    logger.info("Truncated list to final limit of %d. Count: %d", limit, len(final_jobs))
    
    # Write outputs
    if final_jobs:
        try:
            write_csv(final_jobs, args.output)
            logger.info("Successfully outputted CSV results to %s", args.output)
        except Exception as exc:
            logger.error("Failed to write output CSV: %s", exc)
            
        if args.sheet:
            try:
                write_to_sheet(final_jobs, args.sheet)
                logger.info("Successfully published results to Google Sheet.")
            except Exception as exc:
                logger.error("Failed to write to Google Sheet: %s", exc)
    else:
        logger.warning("No jobs matched constraints. Writing empty output targets.")
        # Create empty CSV with headers
        try:
            write_csv([], args.output)
        except Exception:
            pass

if __name__ == "__main__":
    main()

