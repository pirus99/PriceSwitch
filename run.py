"""Development / production entry point for PriceSwitch."""

from __future__ import annotations

import uvicorn

from app.env_config import env_config


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=env_config.host,
        port=env_config.port,
        log_level=env_config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
