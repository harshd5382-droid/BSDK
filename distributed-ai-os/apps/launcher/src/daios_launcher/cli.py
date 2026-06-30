"""CLI entry point for daios-launcher."""

from __future__ import annotations

import argparse
import logging
import webbrowser
from pathlib import Path

import uvicorn

from daios_launcher.app import LauncherApp
from daios_launcher.settings import LauncherSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="DAIOS launcher — one-click node control")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (default: auto-detect from install location)",
    )
    parser.add_argument("--host", default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument("--role", choices=["coordinator", "worker"], default=None)
    parser.add_argument("--token", default=None, help="Cluster control token for LAN API")
    parser.add_argument("--autostart", action="store_true", help="Start node immediately on launch")
    parser.add_argument("--open", action="store_true", help="Open browser on start")
    parser.add_argument("--no-window", action="store_true", help="Suppress browser open (worker service)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    settings = LauncherSettings.load()

    if args.root:
        root = args.root.resolve()
    else:
        import os

        env_root = os.environ.get("DAIOS_ROOT")
        if env_root:
            root = Path(env_root).resolve()
        elif settings.install_dir:
            root = Path(settings.install_dir).resolve()
        else:
            root = Path.cwd().resolve()
            if not (root / "apps" / "launcher").is_dir():
                root = Path(__file__).resolve().parents[4]

    role = args.role or settings.role
    token = args.token or settings.cluster_token
    autostart = args.autostart or settings.autostart_node
    host = args.host or ("0.0.0.0" if role == "worker" else "127.0.0.1")
    port = args.port or settings.launcher_port

    settings.role = role
    settings.install_dir = str(root)
    settings.cluster_token = token or settings.ensure_token()
    settings.autostart_node = autostart
    settings.launcher_port = port
    settings.save()

    launcher = LauncherApp(
        root,
        role=role,
        cluster_token=settings.cluster_token,
        autostart=autostart,
    )
    app = launcher.create_app()

    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"
    if args.open and not args.no_window:
        webbrowser.open(url)

    uvicorn.run(app, host=host, port=port, log_level="debug" if args.verbose else "info")


if __name__ == "__main__":
    main()
