# Installing a BSDK Worker on Windows

This guide walks through joining a Windows PC to a BSDK cluster as a **worker** — a
machine that donates its RAM/VRAM to run one large model over GGML RPC. A worker
never loads the model or answers OpenAI requests itself; it runs only
`ggml-rpc-server.exe` and is driven by the coordinator.

There are two ways to install a worker. Pick one:

| Path | Use when | Effort |
|------|----------|--------|
| **A. Prebuilt `daios-worker.exe`** (recommended) | You want a copy-and-double-click install with autostart, no Python/Git/build tools on the worker | Build the exe once on your dev PC, then copy one file |
| **B. Developer install** (Git + venv) | The worker is also a dev machine and you want the live source tree | Requires Git + Python 3.11+ + internet on the worker |

> **Why the log on the other PC failed:** every `pip install` died with
> `[Errno 11001] getaddrinfo failed` — that machine could not resolve DNS
> (no working internet). It was not a bug in the scripts. See
> [§5 Prerequisites](#5-prerequisites) and [§7 Troubleshooting](#7-troubleshooting).

---

## 1. Ports and paths at a glance

| What | Value |
|------|-------|
| Worker node API (health) | `8001` |
| GGML RPC server (the actual pooled-memory link) | `50052` |
| Launcher control API | `8090` |
| Install root (Path A) | `%LOCALAPPDATA%\BSDK` |
| Logs (Path A) | `%LOCALAPPDATA%\BSDK\logs\` |

The worker must be reachable from the coordinator on **50052** (and 8001/8090 for
health + control). All three are opened in Windows Firewall automatically by the
`.exe` installer.

---

## 2. Path A — Prebuilt `daios-worker.exe` (recommended)

The whole point of the exe is **build once, copy anywhere**. The worker PC needs
**no** Python, Git, Node, or build tools.

### 2a. On your DEV / coordinator PC — build the exe with binaries bundled

> **Important:** the release manifest
> (`packaging/windows/binaries-manifest.json`) still has a placeholder
> `archive_sha256` (`REPLACE_WITH_RELEASE_SHA256`). Until a signed release exists,
> the installer **refuses to download** the GGML binary at runtime (it will not run
> unverifiable binaries). So you **must bundle** the native binaries into the exe at
> build time with `-BinDir`. If you skip this, the worker install fails at
> "Could not obtain a verified worker binary".

From `distributed-ai-os\`, in PowerShell:

```powershell
# One-time: allow scripts in THIS shell only (safe, resets when the window closes)
Set-ExecutionPolicy -Scope Process Bypass

# 1. Build llama.cpp's ggml-rpc-server.exe (+ GGML DLLs). Needs CMake + MSVC.
#    Stage the output into a folder we can bundle from.
#    IMPORTANT: add -Cuda (NVIDIA, needs CUDA Toolkit) or -Vulkan (any GPU,
#    needs Vulkan SDK) if the WORKER has a GPU — without it the rpc-server
#    is CPU-only and the worker's GPU/VRAM can never join the pool.
.\scripts\windows\build-llama-cpp.ps1 -Cuda -InstallDir .\packaging\windows\bin

# 2. Build the worker exe, bundling the binaries staged above.
.\scripts\windows\build-exe.ps1 -BinDir .\packaging\windows\bin
```

Result: `distributed-ai-os\dist\daios-worker.exe` — a single self-contained file
with the RPC server baked in. (If you already have `ggml-rpc-server.exe` + its
DLLs from elsewhere, point `-BinDir` at that folder and skip step 1.)

> Building the exe requires Python 3.11+ and internet **on the dev PC** (PyInstaller
> + package deps come from PyPI). That's fine — this is your online machine. The
> *worker* PC needs neither.

### 2b. Copy to the worker PC

Copy just **`dist\daios-worker.exe`** to the worker (USB stick, network share,
`scp`, anything). Nothing else is required.

### 2c. Run it on the worker PC

Double-click `daios-worker.exe`, **or** from a terminal:

```powershell
.\daios-worker.exe --token YOUR_CLUSTER_TOKEN
```

- `--token` must be the **same cluster token** your coordinator uses (the LAN shared
  secret, `X-DAIOS-Token`). If you omit it, the installer generates one and prints
  it — but then you must give that same token to the coordinator. Easiest is to
  decide the token on the coordinator first and pass it here.
- No admin rights are needed to install. You **may** get one UAC prompt for the
  firewall rules — accept it so the coordinator can discover this worker.

What the installer does automatically:

1. Runs a system check (OS, arch, ports, existing install).
2. Materializes the verified `ggml-rpc-server.exe` under `%LOCALAPPDATA%\BSDK\bin`.
3. Saves settings (role = worker, token) and copies itself to the install dir.
4. Registers a **Task Scheduler job to auto-start at login**.
5. Adds **Windows Firewall** rules for ports 8001 / 50052 / mDNS.
6. Starts the worker service (detached) and waits for it to report healthy.

On success you'll see:

```
[OK] BSDK worker installed and running.
  Health : http://127.0.0.1:8001/health
  Control: http://127.0.0.1:8090
  Logs   : C:\Users\<you>\AppData\Local\BSDK\logs
  Auto-start at login: enabled
```

### 2d. Verify

```powershell
# System report only, no install:
.\daios-worker.exe --check

# Is the node alive?
Invoke-RestMethod http://127.0.0.1:8001/health
```

On the **coordinator**, the worker should now show up automatically (Gen 2 mDNS
discovery) or you add its IP to the coordinator's `peers[]` (Gen 1). Confirm from
the coordinator:

```powershell
Invoke-RestMethod http://<coordinator-ip>:8001/api/v1/membership   # Gen 2
```

---

## 3. Path B — Developer install (Git + venv)

Use this only if the worker is also a machine you develop on. It needs Git,
Python 3.11+, and working internet.

### Option B1 — let the exe do the Git install

```powershell
.\daios-worker.exe --dev --auto-install --token YOUR_CLUSTER_TOKEN
```

`--dev` clones the repo to `%LOCALAPPDATA%\BSDK`, creates a `.venv`, installs the
three packages, and configures the worker. `--auto-install` lets it install missing
Git/Python via `winget` (it always announces before doing so). It prints the exact
command to start the worker when done.

### Option B2 — fully manual

```powershell
# 1. Clone
git clone https://github.com/ciright/BSDK.git
cd BSDK\distributed-ai-os

# 2. One-time: allow scripts in this shell
Set-ExecutionPolicy -Scope Process Bypass

# 3. Install the three packages into a .venv
.\scripts\windows\install-dev.ps1

# 4. Provide the native RPC binary (workers need ggml-rpc-server.exe).
#    Build it locally:
.\scripts\windows\build-llama-cpp.ps1 -InstallDir .\packaging\windows\bin

# 5. Start the worker (role=worker, listen on all interfaces)
.\.venv\Scripts\daios-launcher.exe --root . --role worker --host 0.0.0.0 `
    --token YOUR_CLUSTER_TOKEN --autostart
```

For a static Gen 1 setup you can instead run the node directly against a YAML file
(see `examples/two-node/worker.yaml`):

```powershell
.\.venv\Scripts\daios-node.exe -c examples\two-node\worker.yaml
```

---

## 4. Connecting the worker to the coordinator

BSDK has two membership modes, set by `discovery.enabled` on the coordinator:

- **Gen 2 (auto-discovery, default for the exe):** the worker announces itself over
  mDNS on the LAN (`cluster_name: daios`). The coordinator finds it automatically —
  **nothing to configure on the worker** beyond a matching token and a *Private*
  network profile. The coordinator launches its `llama-server` with
  `--rpc <worker-ip>:50052` using discovered hosts.
- **Gen 1 (static):** discovery off. Add the worker's IP to the **coordinator's**
  `peers[]` list (or `--rpc host:50052`). The worker side is the same.

Either way, the load-bearing connection is the coordinator reaching the worker on
**TCP 50052**.

---

## 5. Prerequisites

**Path A (worker PC):** Windows 10/11 x64. That's it — no Python, Git, or internet
*to run* the worker. (Runtime download of binaries is disabled until a signed
release exists, which is exactly why you bundle them at build time in §2a.)

**Path A (dev PC that builds the exe):** Python 3.11+, internet (PyPI), and for the
llama.cpp binary: CMake + MSVC (Visual Studio Build Tools).

**Path B (worker PC):** Git, Python 3.11+ (`>=3.11`, tested up to 3.14), and working
**internet + DNS** — every `pip install` reaches PyPI. This is the requirement the
failing log did not meet.

---

## 6. Managing the worker

```powershell
# Check status without changing anything
.\daios-worker.exe --check

# Re-run to update/repair (safe; preserves the token)
.\daios-worker.exe

# Uninstall: stop worker, remove autostart + firewall rules, keep data
.\daios-worker.exe --uninstall

# Uninstall and delete all installed data under %LOCALAPPDATA%\BSDK
.\daios-worker.exe --uninstall --purge
```

Logs live in `%LOCALAPPDATA%\BSDK\logs\`:
`worker-install.log`, `worker-service.log`. The cluster token is redacted from logs.

---

## 7. Troubleshooting

### "script is not digitally signed" / "cannot be loaded"
Windows execution policy blocks unsigned `.ps1`. Fix it for the current shell only:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

This is expected on any fresh PC and is safe (`Process` scope resets when the window
closes). The `.exe` path (A) is not a script and never hits this.

### "The term '.\build-exe.ps1\' is not recognized"
That's a typo — a trailing `\` after the filename. Run it **without** the trailing
backslash from inside `scripts\windows\`:

```powershell
.\build-exe.ps1
```

### `[Errno 11001] getaddrinfo failed` during `pip install` (the log's real error)
This is a **DNS / no-internet** failure on that PC — pip could not resolve
`pypi.org`. Diagnose and fix on the worker:

```powershell
# Is it DNS specifically, or no connectivity at all?
Resolve-DnsName pypi.org
Test-NetConnection pypi.org -Port 443

# If DNS fails: flush and switch to a public resolver
ipconfig /flushdns
# Then set the adapter's DNS to 8.8.8.8 / 1.1.1.1 in
# Settings > Network & internet > <adapter> > DNS server assignment
```

Common causes: VPN/proxy, corporate "secure DNS", or firewall software.
**Better fix:** don't build on that PC at all — use **Path A** so the worker needs
no PyPI access.

### "Could not obtain a verified worker binary"
The runtime binary download is disabled (manifest `archive_sha256` is still a
placeholder). Rebuild the exe with the binaries **bundled**:

```powershell
.\scripts\windows\build-llama-cpp.ps1 -InstallDir .\packaging\windows\bin
.\scripts\windows\build-exe.ps1 -BinDir .\packaging\windows\bin
```

### Worker installs but the coordinator can't see it
- Windows says the network is **Public** → auto-discovery is blocked. Set the
  profile to **Private**: Settings > Network & internet > Wi-Fi/Ethernet > Network
  profile type.
- Firewall rules were declined → re-run `.\daios-worker.exe` and accept the UAC
  prompt, or manually allow inbound TCP **50052** and **8001**.
- Different subnets/VLANs → mDNS won't cross them; use Gen 1 static `peers[]` with
  the worker's IP on the coordinator.
- Token mismatch → the worker and coordinator must share the same cluster token.

### Worker started but "did not report healthy"
Check `%LOCALAPPDATA%\BSDK\logs\worker-service.log`. Usually a port already in use
(8001/50052) or the RPC binary failing to load its DLLs.

---

## 8. See also

- `docs/distributed-inference.md` — what GGML RPC does and doesn't distribute,
  the resource-distribution policy, and the two-PC validation procedure
  (including how to verify the worker's GPU is actually used).
- `docs/architecture-gen1.md`, `docs/architecture-gen2.md` — how discovery and RPC
  pooling actually work.
- `docs/operations-guide.md`, `docs/troubleshooting-guide.md` — cluster operations.
- `examples/two-node/` (Gen 1) and `examples/two-node-discovered/` (Gen 2) —
  canonical config references.
