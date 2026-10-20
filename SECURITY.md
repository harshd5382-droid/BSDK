# Security Policy

## Supported versions

BSDK is pre-1.0 prototype software. Only the latest commit on `main` and the most recent tagged release get
security fixes.

| Version | Supported |
|---|---|
| `main` / latest release | ✅ |
| Older releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/harshd5382-droid/BSDK/security/advisories/new). Please
include:

- The affected component (`daios-node`, `daios-launcher`, dashboard, `daios-worker.exe`, scripts)
- The version or commit, your OS, and the node roles involved
- Steps to reproduce, or a proof of concept
- The impact you observed or expect

You can expect an acknowledgement within **7 days**. We'll keep you updated while we investigate and credit
you in the advisory unless you'd rather stay anonymous. Please give us reasonable time to release a fix before
disclosing publicly.

## Threat model

BSDK is designed for **trusted local networks** (home labs, office LANs). Please keep these documented
limitations in mind. Reports that only restate them aren't vulnerabilities, but ideas for hardening them are
very welcome as issues.

| Surface | Current protection | Notes |
|---|---|---|
| GGML RPC (`:50052`) | **None** | llama.cpp's RPC server has no authentication or encryption. Anyone who can reach the port can use the worker's memory and compute. **Never expose it to the internet.** |
| Launcher control API (`:8090`) | Cluster token (`X-DAIOS-Token`) for non-localhost requests | The token is a LAN shared secret. Anyone holding it can start, stop and update workers. |
| Node API / OpenAI proxy (`:8000`) | Optional bearer token (`security.api_token`) | Unauthenticated by default. Enable the token whenever untrusted devices share the network. |
| Node-to-node gossip | Optional dev mTLS (`security.mtls_enabled`) | The dev certificates are self-signed and meant for testing. |
| mDNS discovery (UDP `5353`) | None | Any host on the LAN can advertise itself as a node. |
| Windows installer binaries | SHA-256 verification against `binaries-manifest.json` | Downloads that fail verification are refused. The installer never falls back to an unverified or mock backend. |

### Recommendations for operators

- Run BSDK only on networks you trust. Use a firewall to keep ports `8000`, `8090` and `50052` from being
  reachable outside the LAN.
- Treat the cluster token like a password. Rotate it when people leave or the sharing scope changes.
- Set `security.api_token` if other people's devices can reach the coordinator.
- Download `daios-worker.exe` only from this repository's GitHub Releases.
