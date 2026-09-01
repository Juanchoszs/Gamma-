"""Start the scheduled ingestion loop and Dash dashboard."""
from __future__ import annotations

from gex.ui.app import create_app
from gex.providers.flowtape import TAPE
from gex.infrastructure.logsetup import setup_logging
from gex.providers.rtquote import PUBLIC_QUOTES, QUOTES
from gex.scheduler import start_scheduler
from gex.providers.tickcapture import CAPTURE


def main(host: str = "127.0.0.1", port: int = 8050) -> None:
    setup_logging()
    start_scheduler()
    QUOTES.start()
    PUBLIC_QUOTES.start()
    CAPTURE.start()
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
