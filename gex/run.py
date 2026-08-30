"""Start the scheduled ingestion loop and Dash dashboard."""
from __future__ import annotations

from gex.app import create_app
from gex.flowtape import TAPE
from gex.logsetup import setup_logging
from gex.rtquote import PUBLIC_QUOTES, QUOTES
from gex.scheduler import start_scheduler
from gex.tickcapture import CAPTURE


def main(host: str = "127.0.0.1", port: int = 8050) -> None:
    setup_logging()
    start_scheduler()
    QUOTES.start()
    PUBLIC_QUOTES.start()
    TAPE.start()
    CAPTURE.start()
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
