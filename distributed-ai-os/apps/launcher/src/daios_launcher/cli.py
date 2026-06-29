"""CLI entry point for daios-launcher."""

from __future__ import annotations

import argparse
import logging
import webbrowser
from pathlib import Path

import uvicorn

from daios_launcher.app import LauncherApp


def main() -> None:
    parser = argparse.ArgumentParser(description="DAIOS launcher — one-click node control")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (default: auto-detect from install location)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8090, help="Bind port")
    parser.add_argument("--open", action="store_true", help="Open browser on start")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.root:
        root = args.root.resolve()
    else:
        import os

        env_root = os.environ.get("DAIOS_ROOT")
        if env_root:
            root = Path(env_root).resolve()
        else:
            root = Path.cwd().resolve()
            if not (root / "apps" / "launcher").is_dir():
                root = Path(__file__).resolve().parents[4]

    launcher = LauncherApp(root)
    app = launcher.create_app()

    url = f"http://{args.host}:{args.port}"
    if args.open:
        webbrowser.open(url)

    uvicorn.run(app, host=args.host, port=args.port, log_level="debug" if args.verbose else "info")


if __name__ == "__main__":
    main()
