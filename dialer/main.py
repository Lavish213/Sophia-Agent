from __future__ import annotations

from loguru import logger

from dialer.worker import run_loop

if __name__ == "__main__":
    logger.info("dialer_starting_process")
    run_loop()
