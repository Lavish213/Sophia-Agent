from __future__ import annotations

from loguru import logger

from discovery.worker import run_loop

if __name__ == "__main__":
    logger.info("discovery_starting_process")
    run_loop()
