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
    await worker.run()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
