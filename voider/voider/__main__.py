import logging
import os
import sys

import uvicorn

from voider.config import load_config


def _configure_logging() -> None:
    level_name = os.environ.get("VOIDER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)-22s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    # httpx logs every request at INFO — drowns out our own logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()
    cfg = load_config()
    uvicorn.run(
        "voider.server:app",
        host=cfg.host,
        port=cfg.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
