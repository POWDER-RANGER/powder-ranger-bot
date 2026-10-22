# Security

## What this software controls
A virtual game controller. The threat model is: something other than the
player (a stray process, a network peer, a malformed message, a bug in a
policy) makes the controller do what the player did not authorize.

## Trust boundaries
| Boundary | Control |
| --- | --- |
| Any process -> Governor | Localhost-only ZMQ endpoint; every message is HMAC-SHA256 signed with a per-session key created by the launcher and passed by environment variable |
| Governor input | Strict JSON parsing; malformed or non-finite packets are rejected, counted and logged, never fatal; chunk size is capped |
| Governor -> controller | Single owner of the output adapter; rules in `governor/policy.py`; motor model enforces human-limit timing |
| Authorization | Companion output needs a player-granted delegation; scopes are limited to the active Game Pack |
| Stop | Latched kill switch: Pause hotkey, STOP file at an absolute path (`~/.powder_ranger/STOP`), halt message; halt is latched before neutral output is written |
| Audit | Append-only hash-chained intent log, sealed with a machine-local key; `verify-log` checks both |
| Play mode network | `scripts/lockdown_offline.ps1` blocks egress; `netcheck` verifies from the launcher's Python |

## Known limits
- The NitroGen server (upstream code) binds all interfaces and unpickles requests. `start_nitrogen_server.ps1` refuses to start without its firewall rule. Run it only on the machine that plays.
- The session key is passed in an environment variable, readable by processes of the same user.
- Spoken grants have no confirmation step yet.
- ViGEmBus is retired upstream; existing installs work but receive no fixes.
- A malicious process running as the same user can still send input to the physical device by other means; the Governor does not defend against that.

## Reporting
Open a private security advisory on the GitHub repository (Security tab ->
Report a vulnerability). Include the commit, steps to reproduce, and what
the controller did. Please do not post exploits in public issues.
