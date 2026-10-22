# Architecture

## Processes
| Process | Owns | Never does |
| --- | --- | --- |
| Governor | The output adapter (virtual pad), the intent log, the kill switch | Perception, inference |
| Reflex runner | Capture + NitroGen client | Touch the pad |
| NitroGen server | Model weights, GPU | Anything but answer frames with action chunks |
| Player input / voice / gaze | The player's channels | Touch the pad (they send PLAYER packets) |
| Launcher | Session key, process lifetimes, grants | Send gameplay output |

All gameplay output travels as an `IntentPacket` (JSON, HMAC-signed) to the
Governor over a localhost ZMQ PUSH/PULL socket. There is no other path to
the controller.

## Packet life
1. Verify signature; parse (malformed -> `rejected_message`, counted, session continues).
2. `GovernorPolicy.evaluate`, first deny wins: halted, stale, replayed, player (allow), player-override window, delegation, scope/online rules, focus, confidence, rate limit, menu-button strip.
3. Log the decision in the hash-chained log.
4. Allowed companion packets go to `MotorModel.schedule`; player packets with claims go to the claim table; player packets without claims replace everything.
5. Each tick (default 120 Hz): kill-switch poll, watchdog, `MotorModel.step`, merge claims, write to the adapter.

## Motor scheduling
- A companion command that follows idle time (`episode_gap_ms`, default 500 ms) is an *onset*: it waits one sampled reaction delay (log-normal, median 200 ms, clipped 120-400 ms).
- Within an episode a new chunk starts immediately and supersedes frames still queued from older chunks; frames already due are kept.
- Player output replaces the queue at once, no delay.
- The watchdog fires when nothing has been played for `watchdog_ms` and the queue is empty. It measures played output, not packet arrival.
- Held-stick values are therefore never older than the newest approved chunk.

## Stop path
`KillSwitch.trip` -> `Governor._on_trip`: halt latched and delegations revoked first (so no packet can be accepted), then neutral written under the output lock, then logged. Triggers: Pause hotkey, STOP file (absolute path), `halt` message, any unhandled adapter fault on shutdown.

## Modes
`deployment` enforces `DEPLOYMENT_BOUNDS` (human-limit timing, focus required). `development` is for isolated benchmarking and refuses `online_mode`.

## Game Packs
`packs/<id>/pack.yaml`: process name, pad type, launch command, allowed delegation scopes, online flag. The pack's content hash is logged; the Governor refuses grants outside the pack's scopes.

## Why NitroGen is out-of-process
Its license is noncommercial, its server uses pickle, and it needs its own CUDA environment. Keeping it behind a local socket keeps this repository's code independent of it and lets the Governor treat it as one more untrusted producer.
