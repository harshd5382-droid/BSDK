"""CLI entry point for daios-node."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from daios_protocol.config import load_config

from daios_node.app import NodeApp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Distributed AI OS node daemon (Generation 1)",
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        help="Path to node YAML configuration",
    )
    parser.add_argument(
        "--host",
        help="Override API bind host from config",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override API port from config",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    config = load_config(args.config)
    if args.host:
        config.network.bind_host = args.host
    if args.port:
        config.network.api_port = args.port

    node = NodeApp(config)
    app = node.create_app()

    uvicorn.run(
        app,
        host=config.network.bind_host,
        port=config.network.api_port,
        log_level="debug" if args.verbose else "info",
    )


if __name__ == "__main__":
    main()
