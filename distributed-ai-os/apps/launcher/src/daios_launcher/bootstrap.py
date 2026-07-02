"""DAIOS Windows worker installer / bootstrapper (``daios-worker.exe``).

Double-click on a fresh Windows PC to install, configure, and start a real GGML
RPC worker under ``%LOCALAPPDATA%\\BSDK`` — no admin rights required.

Entry modes (selected by args):

* (default)        install or repair/update, then start the worker and register
                   it to run at login.
* ``--service``    run the worker launcher in-process (used by Task Scheduler).
* ``--run-node``   frozen node-daemon launch (internal; replaces venv daios-node).
* ``--check``      print the system report and exit.
* ``--dev``        legacy Git+venv developer install.
* ``--uninstall``  stop the worker and remove the login task (``--purge`` also
                   deletes installed data).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from daios_launcher import artifacts, firewall_windows, paths, prereqs, system_check
from daios_launcher.autostart_windows import install_task, is_windows, uninstall_task
from daios_launcher.settings import LauncherSettings

logger = logging.getLogger("daios.worker")

# --- Dev (Git) install defaults -------------------------------------------------
DEFAULT_REPO = os.environ.get("DAIOS_REPO_URL", "https://github.com/ciright/BSDK.git")
DEFAULT_BRANCH = os.environ.get("DAIOS_BRANCH", "main")
DEFAULT_DEV_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BSDK"
DEFAULT_DEV_INSTALL = DEFAULT_DEV_ROOT / "distributed-ai-os"

INSTALLED_EXE_NAME = "daios-worker.exe"
MANIFEST_NAME = "binaries-manifest.json"
TOKEN_ENV = "DAIOS_CLUSTER_TOKEN"


# ================================ logging =====================================


class _RedactFilter(logging.Filter):
    """Strip the cluster token out of every log record."""

    def __init__(self, secret: str | None) -> None:
        super().__init__()
        self.secret = secret

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if self.secret:
            if isinstance(record.msg, str) and self.secret in record.msg:
                record.msg = record.msg.replace(self.secret, "***")
            if record.args:
                record.args = tuple(
                    str(a).replace(self.secret, "***") if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def _setup_logging(token: str | None, log_name: str, verbose: bool = False) -> Path:
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    log_path = paths.logs_dir() / log_name
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    redact = _RedactFilter(token)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(redact)
    root.addHandler(fh)
    # The exe is windowed: in service mode there is no console and sys.stderr
    # is None, so only mirror to a stream when one actually exists.
    if sys.stderr is not None:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(redact)
        root.addHandler(ch)
    return log_path


# ============================ double-click console ============================


def _ensure_console() -> None:
    """Give interactive modes (install/uninstall/--check) a console to print to.

    The exe is built windowed so the background service never shows a window.
    When run from a terminal we attach to it; when double-clicked we allocate a
    fresh console. When output is already redirected (e.g. the remote-update
    installer spawned detached with a log file), leave everything alone —
    allocating a console there would flash a window on the worker PC.
    """
    if not is_windows() or not paths.is_frozen():
        return
    if sys.stdout is not None:
        return  # already have a console or redirected output
    import ctypes

    kernel32 = ctypes.windll.kernel32
    if kernel32.GetConsoleWindow():
        return
    attach_parent = ctypes.c_uint(-1).value  # ATTACH_PARENT_PROCESS
    if not kernel32.AttachConsole(attach_parent) and not kernel32.AllocConsole():
        return
    try:
        sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    except OSError:
        pass


def _console_owned() -> bool:
    """True when we likely own the console (double-clicked from Explorer)."""
    if not is_windows():
        return False
    try:
        import ctypes

        arr = (ctypes.c_uint * 2)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(arr, 2)
        return count <= 1
    except Exception:
        return False


def _pause(message: str = "") -> None:
    if message:
        print(message)
    if _console_owned():
        try:
            input("\nPress Enter to close this window...")
        except (EOFError, KeyboardInterrupt):
            pass


# ============================== install paths ================================


def installed_exe_path() -> Path:
    return paths.install_root() / INSTALLED_EXE_NAME


def _manifest_path() -> Path | None:
    """Locate the binaries manifest (bundled in the exe, or in the source tree)."""
    bundled = paths.bundled_dir()
    if bundled:
        cand = bundled / MANIFEST_NAME
        if cand.is_file():
            return cand
    # Source tree fallback (dev runs).
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "packaging" / "windows" / MANIFEST_NAME
        if cand.is_file():
            return cand
    return None


def _bundled_bin() -> Path | None:
    bundled = paths.bundled_dir()
    return (bundled / "bin") if bundled else None


# ============================== token handling ===============================


def _resolve_token(cli_token: str | None, settings: LauncherSettings) -> str:
    """Token precedence: --token > env > existing settings > generated."""
    token = cli_token or os.environ.get(TOKEN_ENV) or settings.cluster_token
    if token:
        settings.cluster_token = token
        settings.save()
        return token
    return settings.ensure_token()


# ============================ binary acquisition =============================


def ensure_real_backend() -> Path:
    """Guarantee a verified ggml-rpc-server.exe in the install bin dir.

    Raises :class:`artifacts.ArtifactError` if no verified real binary can be
    produced. The caller MUST treat that as fatal — never mock-fallback.
    """
    manifest_path = _manifest_path()
    if not manifest_path:
        raise artifacts.MissingBinaryError(
            "binaries-manifest.json not found; cannot locate the worker binary."
        )
    manifest = artifacts.load_manifest(manifest_path)
    return artifacts.ensure_worker_binaries(
        manifest, paths.bin_dir(), bundled_bin=_bundled_bin()
    )


# =============================== service start ===============================


def _health_ok(port: int, timeout: float = 30.0) -> bool:
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    return False


def _stop_running_worker() -> None:
    """Terminate any running worker/launcher processes (for safe restart)."""
    try:
        import psutil
    except ImportError:
        return
    exe = str(installed_exe_path()).lower()
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            info = proc.info
            pexe = (info.get("exe") or "").lower()
            cmd = " ".join(info.get("cmdline") or []).lower()
            if pexe == exe or ("daios-worker" in (info.get("name") or "").lower()
                               and ("--service" in cmd or "--run-node" in cmd)):
                if proc.pid != os.getpid():
                    proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    from daios_launcher.platform_utils import kill_port_listeners

    for port in (system_check.API_PORT, system_check.RPC_PORT, system_check.LAUNCHER_PORT):
        kill_port_listeners(port)


def _spawn_service_detached(installed_exe: Path) -> subprocess.Popen:
    """Start the worker service so it survives the installer process exiting."""
    log_path = paths.logs_dir() / "worker-service.log"
    creationflags = 0
    if is_windows():
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    log_handle = open(log_path, "ab")
    return subprocess.Popen(
        [str(installed_exe), "--service"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def _run_service(token: str, verbose: bool = False) -> int:
    """Run the worker launcher in-process (Task Scheduler / detached child)."""
    install_root = paths.install_root()
    os.environ["DAIOS_ROOT"] = str(install_root)
    # Production guard: the launcher refuses to mock when this is set.
    os.environ.setdefault("DAIOS_REQUIRE_REAL_BACKEND", "1")
    sys.argv = [
        "daios-launcher",
        "--root", str(install_root),
        "--role", "worker",
        "--host", "0.0.0.0",
        "--token", token,
        "--autostart",
        "--no-window",
    ]
    if verbose:
        sys.argv.append("--verbose")
    from daios_launcher import cli as launcher_cli

    launcher_cli.main()
    return 0


def _run_node(argv: list[str]) -> int:
    """Frozen node-daemon launch (replaces the venv ``daios-node`` binary)."""
    sys.argv = ["daios-node", *argv]
    from daios_node import cli as node_cli

    node_cli.main()
    return 0


# ============================== install flow =================================


def _copy_self_to_install(installed_exe: Path) -> None:
    """Copy the running exe into the install dir (so autostart uses a stable path)."""
    if not paths.is_frozen():
        return
    source = Path(sys.executable).resolve()
    if source == installed_exe.resolve():
        return
    installed_exe.parent.mkdir(parents=True, exist_ok=True)
    tmp = installed_exe.with_suffix(".exe.new")
    shutil.copy2(source, tmp)
    # During a remote update the old service process (which spawned us) may
    # still be exiting and holding the installed exe locked; retry briefly.
    for attempt in range(10):
        try:
            os.replace(tmp, installed_exe)  # atomic on the same volume
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(1.0)


def install_or_update(
    token_arg: str | None, *, dev: bool, verbose: bool, args: argparse.Namespace
) -> int:
    settings = LauncherSettings.load()
    token = _resolve_token(token_arg, settings)
    _setup_logging(token, "worker-install.log", verbose)

    report = system_check.check_system(paths.install_root())
    print(system_check.format_report(report))
    logger.info("System: %s %s / %s", report.os_name, report.os_release, report.architecture)

    blocking = report.blocking_errors()
    if blocking:
        for err in blocking:
            logger.error(err)
        _pause("\nInstallation cannot continue:\n  - " + "\n  - ".join(blocking))
        return 2

    if dev:
        return _dev_install(args, token)

    if not paths.is_frozen():
        logger.error(
            "Self-contained install requires the packaged daios-worker.exe. "
            "From source, use --dev (Git+venv) or build the exe with "
            "scripts\\windows\\build-exe.ps1."
        )
        _pause()
        return 2

    updating = report.already_installed
    action = "Updating" if updating else "Installing"
    logger.info("%s BSDK worker under %s", action, paths.install_root())
    paths.ensure_layout()

    if updating:
        # Stop the running worker before swapping files (Windows locks running exes).
        _stop_running_worker()
        time.sleep(1.0)

    # 1. Materialize a verified real backend (download+verify or bundled). Atomic:
    #    a failure here leaves any previous binary in place and usable.
    try:
        rpc = ensure_real_backend()
        logger.info("Verified worker binary: %s", rpc)
    except artifacts.ArtifactError as exc:
        logger.error("Could not obtain a verified worker binary: %s", exc)
        _pause(
            "\nThe real GGML RPC worker binary could not be installed. The mock "
            "backend is NOT used as a substitute. See the log for details:\n"
            f"  {paths.logs_dir() / 'worker-install.log'}"
        )
        return 3

    # 2. Persist settings (preserve token across updates).
    installed_exe = installed_exe_path()
    settings.role = "worker"
    settings.autostart_node = True
    settings.cluster_token = token
    settings.launcher_port = system_check.LAUNCHER_PORT
    settings.install_dir = str(paths.install_root())
    settings.save()

    # 3. Copy the installer exe to the stable install path for autostart.
    try:
        _copy_self_to_install(installed_exe)
    except OSError as exc:
        logger.warning("Could not copy exe into install dir (%s); using current path", exc)
        installed_exe = Path(sys.executable)

    # 4. Register login autostart (idempotent — never duplicates).
    if is_windows():
        ok, msg = install_task(installed_exe)
        logger.info("Autostart task: %s (%s)", "ok" if ok else "failed", msg)

    # 5. Open Windows Firewall for inbound mDNS + API + RPC (idempotent; one UAC
    #    prompt at most). Without this, coordinators cannot auto-discover this
    #    worker and users end up typing IPs manually. Not fatal if declined.
    if is_windows():
        fw_ok, fw_msg = firewall_windows.ensure_rules(
            installed_exe, paths.bin_dir() / "ggml-rpc-server.exe"
        )
        logger.info("Firewall rules: %s", "ok" if fw_ok else "NOT added")
        if not fw_ok:
            print(f"\n[WARN] {fw_msg}\n")
        if firewall_windows.active_profile_is_public():
            print(
                "\n[WARN] This network is set to 'Public' in Windows, which blocks "
                "LAN discovery. Set it to 'Private' (Settings > Network & internet > "
                "Wi-Fi/Ethernet > Network profile type) for auto-discovery to work.\n"
            )

    # 6. Start the worker now (detached so it outlives this installer).
    if report.already_running:
        _stop_running_worker()
        time.sleep(1.0)
    logger.info("Starting worker service...")
    _spawn_service_detached(installed_exe)

    healthy = _health_ok(system_check.API_PORT, timeout=40.0)
    if healthy:
        logger.info("Worker is healthy on http://127.0.0.1:%s/health", system_check.API_PORT)
        print(
            f"\n[OK] BSDK worker {'updated' if updating else 'installed'} and running.\n"
            f"  Health : http://127.0.0.1:{system_check.API_PORT}/health\n"
            f"  Control: http://127.0.0.1:{system_check.LAUNCHER_PORT}\n"
            f"  Logs   : {paths.logs_dir()}\n"
            f"  Auto-start at login: enabled\n"
        )
        _pause()
        return 0

    logger.error("Worker did not become healthy within timeout")
    _pause(
        "\nThe worker started but did not report healthy. Check the logs:\n"
        f"  {paths.logs_dir() / 'worker-service.log'}"
    )
    return 4


# ============================== uninstall flow ===============================


def uninstall(purge: bool) -> int:
    _setup_logging(None, "worker-uninstall.log")
    logger.info("Stopping worker processes...")
    _stop_running_worker()
    if is_windows():
        ok, msg = uninstall_task()
        logger.info("Autostart task removal: %s (%s)", "ok" if ok else "failed", msg)
        fw_ok, fw_msg = firewall_windows.remove_rules()
        logger.info("Firewall rules removal: %s (%s)", "ok" if fw_ok else "failed", fw_msg)
    if purge:
        root = paths.install_root()
        logger.info("Purging %s", root)
        # Release our own log file handle under root, else Windows refuses removal.
        for handler in list(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)
        shutil.rmtree(root, ignore_errors=True)
        from daios_launcher.settings import SETTINGS_PATH

        Path(SETTINGS_PATH).unlink(missing_ok=True)
        print("BSDK worker uninstalled and data purged.")
    else:
        print("BSDK worker uninstalled. Installed data preserved (use --purge to remove).")
    _pause()
    return 0


# ============================ dev (Git) install ==============================


def _run(cmd: list[str], cwd: Path | None = None, timeout: float = 600.0) -> tuple[int, str]:
    result = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        timeout=timeout, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


def _dev_install(args: argparse.Namespace, token: str) -> int:
    """Legacy Git + venv developer install, with version-validated prerequisites."""
    ok, tools = prereqs.ensure_dev_prerequisites(
        auto_install=args.auto_install, on_message=lambda m: logger.info(m)
    )
    if not ok:
        _pause(
            "\nMissing prerequisites. Re-run with --auto-install to install them via "
            "winget, or install Git and Python 3.11+ manually."
        )
        return 2

    from daios_launcher.update import pull_latest, reinstall_deps

    install_dir = args.install_dir
    repo_root = install_dir.parent
    repo_root.mkdir(parents=True, exist_ok=True)
    if not (repo_root / ".git").is_dir():
        code, out = _run(["git", "clone", "--depth", "1", "-b", args.branch, args.repo, str(repo_root)])
        if code != 0:
            code, out = _run(["git", "clone", "--depth", "1", args.repo, str(repo_root)])
        if code != 0:
            logger.error("git clone failed: %s", out)
            _pause()
            return 3
    else:
        pull = pull_latest(repo_root, branch=args.branch)
        if not pull.ok:
            logger.warning("git pull failed: %s", "; ".join(pull.messages))

    if not install_dir.is_dir():
        logger.error("Expected project at %s", install_dir)
        _pause()
        return 3

    venv_python = (
        install_dir / ".venv" / ("Scripts/python.exe" if is_windows() else "bin/python")
    )
    if not venv_python.is_file():
        code, out = _run([sys.executable if not paths.is_frozen() else "python",
                          "-m", "venv", str(install_dir / ".venv")], cwd=install_dir)
        if code != 0:
            logger.error("venv creation failed: %s", out)
            _pause()
            return 3
    reinstall = reinstall_deps(install_dir)
    if not reinstall.ok:
        logger.error("dependency install failed: %s", "; ".join(reinstall.messages))
        _pause()
        return 3

    settings = LauncherSettings.load()
    settings.role = "worker"
    settings.autostart_node = True
    settings.cluster_token = token
    settings.install_dir = str(install_dir)
    settings.save()
    logger.info("Dev install complete at %s", install_dir)
    print(
        "\n[OK] Developer install complete. Start the worker with:\n"
        f"  {venv_python} -m daios_launcher.cli --root {install_dir} "
        "--role worker --host 0.0.0.0 --autostart --no-window\n"
    )
    _pause()
    return 0


# ================================== main =====================================


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daios-worker", description="BSDK Windows worker installer"
    )
    parser.add_argument("--service", action="store_true", help="Run the worker (service mode)")
    # Accepted as an alias so the legacy autostart command never errors.
    parser.add_argument("--no-window", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-node", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="Print system report and exit")
    parser.add_argument("--uninstall", action="store_true", help="Stop worker and remove autostart")
    parser.add_argument("--purge", action="store_true", help="With --uninstall: delete installed data")
    parser.add_argument("--dev", action="store_true", help="Legacy Git + venv developer install")
    parser.add_argument("--auto-install", action="store_true", help="Allow winget to install missing dev tools")
    parser.add_argument("--token", default=None, help="Cluster control token")
    parser.add_argument("--install-dir", type=Path, default=DEFAULT_DEV_INSTALL, help=argparse.SUPPRESS)
    parser.add_argument("--repo", default=DEFAULT_REPO, help=argparse.SUPPRESS)
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help=argparse.SUPPRESS)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main() -> None:
    # --run-node passes the remaining argv straight to the node daemon.
    if "--run-node" in sys.argv:
        idx = sys.argv.index("--run-node")
        sys.exit(_run_node(sys.argv[idx + 1:]))

    parser = _build_parser()
    args, _unknown = parser.parse_known_args()

    # Interactive modes need a console (the exe is windowed); service mode must
    # stay invisible, so only set one up when not running as the service.
    if not (args.service or args.no_window):
        _ensure_console()

    if args.check:
        report = system_check.check_system(paths.install_root())
        print(system_check.format_report(report))
        sys.exit(0 if report.supported else 2)

    if args.service or args.no_window:
        settings = LauncherSettings.load()
        token = _resolve_token(args.token, settings)
        _setup_logging(token, "worker-service.log", args.verbose)
        sys.exit(_run_service(token, args.verbose))

    if args.uninstall:
        sys.exit(uninstall(args.purge))

    try:
        sys.exit(install_or_update(args.token, dev=args.dev, verbose=args.verbose, args=args))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # last-resort: keep console open on a crash
        logging.getLogger("daios.worker").exception("Unexpected failure: %s", exc)
        _pause(f"\nUnexpected error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
