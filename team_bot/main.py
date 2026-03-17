from __future__ import annotations

import asyncio
import logging

from .config import BotConfig
from .worker import TeamBotWorker


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _main() -> None:
    config = BotConfig.from_env()
    configure_logging(config.log_level)
    worker = TeamBotWorker(config)
    try:
        await worker.run()
    finally:
        if worker.sio.connected:
            await worker.sio.disconnect()


def main() -> None:
    try:
        asyncio.run(_main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        return


if __name__ == "__main__":
    main()
