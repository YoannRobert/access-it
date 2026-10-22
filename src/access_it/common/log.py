"""Logging of the ETL: one logger per module, configured once by the scripts.

Modules get their logger with logging.getLogger(__name__); the scripts call
setup_logging() once, before running a step. Messages go to the standard
output, like the outputs of the scripts, so that they stay in order.
"""

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Send the messages of the package to the standard output, with time and level.

    Calling it again replaces the previous configuration (no duplicated lines).

    Args:
        level: Lowest level written (logging.DEBUG for the detailed outputs).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)
