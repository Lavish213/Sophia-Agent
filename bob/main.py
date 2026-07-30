from __future__ import annotations

from loguru import logger

from bob.worker import run_loop

if __name__ == "__main__":
    logger.info("bob_intelligence_starting")
    run_loop()
