"""Command line entry point: python -m powder_ranger <command>

  launch      start the Governor and the reflex runner, grant the delegation
  governor    run the Governor process alone
  reflex      run the NitroGen reflex runner alone
  padtest     drive the virtual pad through a slow, labelled test pattern
  netcheck    check that this Python cannot reach the internet
  verify-log  verify an intent log's hash chain and seal
  stop        trip the kill switch by creating the STOP file
"""

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .config import DEFAULT_CONFIG, load_settings, validate_settings
from .intent import Delegation, GamepadFrame, IntentPacket, Source

KEY_ENV = "PR_SESSION_KEY"


def _config_hash(config: str | None, profile: str | None) -> str:
    h = hashlib.sha256()
    for p in (config or DEFAULT_CONFIG, profile):
        if p:
            h.update(Path(p).read_bytes())
    return h.hexdigest()


def _session_key() -> bytes:
    raw = os.environ.get(KEY_ENV)
    if not raw:
        sys.exit(f"{KEY_ENV} is not set. Start through `launch`, or set it for manual runs.")
    return bytes.fromhex(raw)


# ---------------------------------------------------------------------------
def cmd_governor(a: argparse.Namespace) -> int:
    from .governor.governor import Governor
    from .governor.intent_log import IntentLog, load_or_create_log_key
    from .governor.safety import FocusChecker, KillSwitch
    from .motor.model import MotorModel
    from .output.adapters import make_adapter

    s = load_settings(a.config, a.profile)
    if a.online:
        s.governor.online_mode = True
    pack_info = {}
    if a.pack:
        from .packs import load_pack
        pk = load_pack(a.pack)
        pack_info = pk.session_info()
        if pk.online:
            s.governor.online_mode = True
    output = a.output or s.output
    problems = validate_settings(s, output)
    if problems:
        print("Refusing to start:\n  " + "\n  ".join(problems))
        return 6
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_dir = Path(s.log_dir)
    log = IntentLog(log_dir / f"session-{stamp}.jsonl")
    kill = KillSwitch(s.stop_file)
    if Path(s.stop_file).exists():
        print(f"Kill switch file {s.stop_file} exists; delete it before starting.")
        return 2
    hot = kill.start_hotkeys()
    adapter = make_adapter(output, record_path=log_dir / f"dryrun-{stamp}.jsonl" if output == "dryrun" else None,
                           invert_y=s.invert_y)
    focus = FocusChecker(a.process, assume_focused_off_windows=(output == "dryrun"))
    gov = Governor(s.governor, MotorModel(s.motor), adapter, log, kill, focus,
                   seal_key=load_or_create_log_key(),
                   session_info={"config_hash": _config_hash(a.config, a.profile),
                                 "profile": s.profile_name, "mode": s.mode, "target_process": a.process,
                                 "hotkeys": hot, **pack_info})
    print(f"Governor up on {s.endpoint} | mode={s.mode} | output={adapter.name} | log={log.path}")
    print("Kill switch: Pause key" if hot else
          f"Kill switch hotkey unavailable; use `python -m powder_ranger stop` (creates {s.stop_file})")
    gov.serve(s.endpoint, _session_key(), tick_hz=s.tick_hz)
    print(f"Governor stopped: {gov.stats}")
    return 0


def cmd_reflex(a: argparse.Namespace) -> int:
    from .governor.client import GovernorClient
    from .runners import nitrogen

    s = load_settings(a.config, a.profile)
    client = GovernorClient(s.endpoint, _session_key(), Source.REFLEX)
    try:
        nitrogen.run(client, a.process, a.delegation, port=a.port,
                     metrics_path=Path(s.log_dir) / "reflex_metrics.csv")
    finally:
        client.close()
    return 0


def cmd_launch(a: argparse.Namespace) -> int:
    from .governor.client import GovernorClient

    if a.require_offline and _netcheck(quiet=True) != 0:
        print("Refusing to launch: this Python can reach the internet (run scripts/lockdown_offline.ps1).")
        return 3
    s = load_settings(a.config, a.profile)
    pack = None
    if a.pack:
        from .packs import load_pack
        try:
            pack = load_pack(a.pack)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Refusing to launch: {exc}")
            return 8
        a.process = a.process or pack.process
        a.output = a.output or pack.output
        if pack.online:
            s.governor.online_mode = True
        if a.delegate not in pack.allowed_scopes:
            print(f"Refusing: pack {pack.id} does not allow '{a.delegate}' (allowed: {', '.join(pack.allowed_scopes)})")
            return 4
        print(f"Pack: {pack.title} v{pack.version} ({pack.content_hash[:12]})")
    if not a.process:
        print("Refusing to launch: give --process or --pack")
        return 8
    problems = validate_settings(s, a.output or s.output)
    if problems:
        print("Refusing to launch:\n  " + "\n  ".join(problems))
        return 6
    if s.governor.online_mode and a.delegate in s.governor.blocked_scopes_online:
        print(f"Refusing: delegation '{a.delegate}' is not allowed in online mode.")
        return 4

    player_args: list[str] | None = None
    if a.player_input == "xinput":
        from .inputs.player import pick_player_slot, xinput_connected_slots
        try:
            slot = a.player_slot if a.player_slot is not None else pick_player_slot(xinput_connected_slots())
        except RuntimeError as exc:
            print(f"Refusing to launch: {exc}")
            return 7
        player_args = ["player", "--source", "xinput", "--slot", str(slot)]
        print(f"Player controller: XInput slot {slot} (chosen before the virtual pad is created)")
    elif a.player_input == "keyboard":
        player_args = ["player", "--source", "keyboard"]
    elif a.player_input == "gaze":
        player_args = ["player", "--source", "gaze"]
    if player_args is not None and a.steady:
        player_args.append("--steady")

    if a.start_game:
        if pack is None or not pack.launch_exe:
            print("Refusing: --start-game needs a pack with launch.exe")
            return 8
        print(f"Starting {pack.title}; waiting {pack.ready_after_s:.0f} s for it to load...")
        subprocess.Popen([pack.launch_exe, *pack.launch_args])
        time.sleep(pack.ready_after_s)

    env = dict(os.environ, **{KEY_ENV: os.urandom(32).hex()})
    common = [*(["--config", a.config] if a.config else []), *(["--profile", a.profile] if a.profile else [])]
    gov = subprocess.Popen([sys.executable, "-m", "powder_ranger", *common, "governor", "--process", a.process,
                            *(["--output", a.output] if a.output else []),
                            *(["--pack", str(pack.path)] if pack else []),
                            *(["--online"] if s.governor.online_mode else [])], env=env)
    time.sleep(1.5)
    if gov.poll() is not None:
        print("Governor failed to start.")
        return 5

    control = GovernorClient(s.endpoint, bytes.fromhex(env[KEY_ENV]), Source.SYSTEM)
    delegation = Delegation(id=f"launch-{int(time.time())}", scope=a.delegate, granted_at=time.monotonic(),
                            note="granted by the player at launch")
    control.grant(delegation)
    print(f"Delegation granted: {delegation.scope} ({delegation.id})")

    player = (subprocess.Popen([sys.executable, "-m", "powder_ranger", *common, *player_args], env=env)
              if player_args is not None else None)
    voice = (subprocess.Popen([sys.executable, "-m", "powder_ranger", *common, "voice"], env=env)
             if a.voice else None)
    reflex = subprocess.Popen([sys.executable, "-m", "powder_ranger", *common, "reflex", "--process", a.process,
                               "--delegation", delegation.id, "--port", str(a.port)], env=env)
    try:
        while gov.poll() is None and reflex.poll() is None:
            if player is not None and player.poll() is not None:
                print("Player input process exited: halting the companion (the player must be able to take over).")
                control.halt("player input lost")
                break
            time.sleep(0.25)
        if reflex.poll() is not None:
            print(f"Reflex runner exited (code {reflex.returncode}).")
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        control.revoke()
        for proc in (reflex, player, voice):
            if proc is not None and proc.poll() is None:
                proc.terminate()
        control.shutdown()
        try:
            gov.wait(timeout=5)
        except subprocess.TimeoutExpired:
            gov.terminate()
        control.close()
    print()
    try:
        cmd_report(argparse.Namespace(path=None, metrics=None, config=a.config, profile=a.profile))
    except SystemExit:
        pass
    return 0


def cmd_padtest(a: argparse.Namespace) -> int:
    """Player-sourced test pattern. Watch it in Windows 'Set up USB game controllers' (joy.cpl)."""
    from .governor.governor import Governor
    from .governor.intent_log import IntentLog
    from .governor.policy import GovernorConfig
    from .governor.safety import KillSwitch
    from .motor.model import MotorModel
    from .output.adapters import make_adapter

    s = load_settings(a.config, a.profile)
    adapter = make_adapter(a.output or s.output, invert_y=s.invert_y)
    log = IntentLog(Path(s.log_dir) / f"padtest-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    kill = KillSwitch(s.stop_file)
    kill.start_hotkeys()
    from .governor.intent_log import load_or_create_log_key
    gov = Governor(GovernorConfig(require_focus=False), MotorModel(s.motor), adapter, log, kill, lambda: True,
                   seal_key=load_or_create_log_key(), session_info={"purpose": "padtest"})
    steps = [
        ("Left stick UP", GamepadFrame(ly=0.8)), ("Left stick DOWN", GamepadFrame(ly=-0.8)),
        ("Left stick LEFT", GamepadFrame(lx=-0.8)), ("Left stick RIGHT", GamepadFrame(lx=0.8)),
        ("Right stick UP", GamepadFrame(ry=0.8)), ("Right stick RIGHT", GamepadFrame(rx=0.8)),
        ("Left trigger", GamepadFrame(lt=1.0)), ("Right trigger", GamepadFrame(rt=1.0)),
        *[(f"Button {b}", GamepadFrame(buttons=frozenset({b})))
          for b in ("SOUTH", "EAST", "WEST", "NORTH", "LEFT_SHOULDER", "RIGHT_SHOULDER",
                    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT")],
    ]
    print("Open joy.cpl > Properties to watch the virtual pad. Pause key stops the test.")
    seq = 0
    try:
        for label, frame in [*steps, ("Neutral", GamepadFrame())]:
            print(f"  {label}")
            end = time.monotonic() + a.hold
            while time.monotonic() < end and not kill.tripped:
                seq += 1
                gov.handle("intent", IntentPacket(seq=seq, source=Source.PLAYER, created_at=time.monotonic(),
                                                  ttl_ms=200, frames=(frame,), note=f"padtest: {label}").to_dict())
                for _ in range(6):
                    gov.tick()
                    time.sleep(1 / 120)
            if kill.tripped:
                print("Kill switch tripped; stopping.")
                break
    finally:
        gov.close()
    print("Pad test finished. If UP showed as DOWN, set invert_y: true in config/default.yaml.")
    return 0


def cmd_player(a: argparse.Namespace) -> int:
    """Player input -> Governor as PLAYER packets (always outrank the companion)."""
    import yaml
    from .governor.client import GovernorClient
    from .inputs.player import KeyboardSource, PlayerInputLoop, XInputSource

    s = load_settings(a.config, a.profile)
    if a.source == "gaze":
        import json as _json
        from .inputs.gaze import GazeCalibration, GazeSource, GazeStick, mediapipe_features
        if not a.gaze_cal or not Path(a.gaze_cal).exists():
            sys.exit("gaze needs --gaze-cal (run `python -m powder_ranger gaze-calibrate` first)")
        data = _json.loads(Path(a.gaze_cal).read_text())
        w, h = data["screen"]
        src = GazeSource(mediapipe_features(a.face_model), GazeCalibration.from_dict(data["calibration"]),
                         GazeStick(w, h))
    elif a.source == "xinput":
        if a.slot is None:
            sys.exit("--slot is required (launch picks it before the virtual pad exists)")
        src = XInputSource(a.slot)
    else:
        prof = yaml.safe_load(Path(a.profile).read_text()) if a.profile else {}
        keymap = ((prof or {}).get("player_input") or {}).get("keymap")
        if not keymap:
            sys.exit("keyboard input needs player_input.keymap in the profile")
        src = KeyboardSource(keymap)
    client = GovernorClient(s.endpoint, _session_key(), Source.PLAYER)
    loop = PlayerInputLoop(src, lambda f, claims=(): client.send_frames([f], frame_dt_ms=1000 / 120, ttl_ms=150,
                                                                         note=f"player:{src.name}", claims=claims),
                           presence=client.presence, steady=a.steady)
    print(f"Player input: {src.name}{' (steady)' if a.steady else ''}")
    try:
        loop.run(hz=120)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
    return 0


def cmd_voice(a: argparse.Namespace) -> int:
    """Local voice commands: stop, resume, you play, my turn, jump, status."""
    from .governor.client import GovernorClient
    from .inputs.voice import Speaker, VoiceDispatcher, VoiceListener

    s = load_settings(a.config, a.profile)
    key = _session_key()
    control = GovernorClient(s.endpoint, key, Source.PLAYER)
    speaker = Speaker(enabled=not a.no_tts)
    disp = VoiceDispatcher(control.send_message,
                           lambda fs: control.send_frames(fs, frame_dt_ms=100, ttl_ms=300, note="voice tap"),
                           speaker.say)

    def on_text(text: str) -> None:
        cmd = disp.handle_text(text)
        print(f"heard: {text!r} -> {cmd.verb if cmd else 'no command'}")

    print(f"Voice: loading {a.model} (first run downloads it; play mode must have it cached)")
    listener = VoiceListener(on_text, model=a.model)
    speaker.say("Listening.")
    try:
        listener.run()
    except KeyboardInterrupt:
        pass
    finally:
        speaker.close()
        control.close()
    return 0


def cmd_calibrate(a: argparse.Namespace) -> int:
    """record: capture the player's own pad. fit: turn a recording into a profile."""
    from .motor import calibrate as cal
    out_dir = Path("config") / "profiles"
    if a.action == "record":
        from .inputs.player import XInputSource, pick_player_slot, xinput_connected_slots
        slot = a.slot if a.slot is not None else pick_player_slot(xinput_connected_slots())
        path = Path(a.file or f"logs/calibration-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Recording XInput slot {slot} for {a.seconds:.0f} s. Play normally: move the sticks, "
              "hold them still, tap and mash buttons.")
        n = cal.record(XInputSource(slot), path, a.seconds)
        print(f"Recorded {n} samples to {path}")
        return 0
    if a.action == "reaction":
        from .inputs.player import XInputSource, pick_player_slot, xinput_connected_slots
        slot = a.slot if a.slot is not None else pick_player_slot(xinput_connected_slots())
        times = cal.run_reaction_test(XInputSource(slot), trials=a.trials)
        profile, report = cal.fit_reaction(times)
        print(f"trials: {report['trials']}  valid: {report['valid']}  anticipations: {report['anticipations']}")
        if "fitted" not in report:
            print(f"  {report['kept_default']}")
            return 1
        for k, v in report["fitted"].items():
            print(f"  fitted {k}: {v}")
        name = a.name or "fitted"
        out = out_dir / f"local_{name}.yaml"
        if out.exists():
            import yaml
            data = yaml.safe_load(out.read_text()) or {}
            data.setdefault("motor", {}).update(report["fitted"])
            out.write_text(yaml.safe_dump(data, sort_keys=False))
        else:
            out.write_text(cal.profile_yaml(profile, name))
        print(f"Profile updated: {out}")
        return 0
    if not a.file:
        sys.exit("fit needs --file <recording.jsonl>")
    profile, report = cal.fit_profile(a.file)
    name = a.name or "fitted"
    out = out_dir / f"local_{name}.yaml"
    out.write_text(cal.profile_yaml(profile, name))
    print(f"samples: {report['samples']}  duration: {report['duration_s']:.0f} s")
    for k, v in report["fitted"].items():
        print(f"  fitted  {k}: {v}")
    for k in report["kept_default"]:
        print(f"  default {k} (not enough evidence in the recording)")
    for k in report["not_fitted"]:
        print(f"  not fitted: {k}")
    print(f"Profile written: {out} (git-ignored; stays on this machine)")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    import json as _json
    from .report import build_report, format_report
    path = Path(a.path) if a.path else max(Path(load_settings(a.config, a.profile).log_dir).glob("session-*.jsonl"),
                                           key=lambda p: p.stat().st_mtime, default=None)
    if path is None:
        sys.exit("no session logs found")
    metrics = Path(a.metrics) if a.metrics else path.parent / "reflex_metrics.csv"
    r = build_report(path, metrics)
    print(format_report(r))
    out = path.with_suffix(".report.json")
    out.write_text(_json.dumps(r, indent=2))
    print(f"\nwritten: {out}")
    return 0 if r["integrity"]["chain_ok"] else 1


def cmd_gaze_calibrate(a: argparse.Namespace) -> int:
    import json as _json
    from .inputs.gaze import mediapipe_features, run_calibration
    if not Path(a.face_model).exists():
        sys.exit(f"face model not found: {a.face_model} (download face_landmarker.task in prep mode)")
    cal, report = run_calibration(mediapipe_features(a.face_model))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps({"calibration": cal.to_dict(), "screen": report["screen"], "report": report}))
    print(f"points used {report['points_used']}/9, missed {report['points_missed']}, "
          f"error {report['rms_px']} px RMS -> {out}")
    if report["rms_px"] > 120:
        print("Error is high: check lighting and keep your head still, then run it again.")
    return 0


def cmd_packs(a: argparse.Namespace) -> int:
    from .packs import list_packs, load_pack
    for pid in list_packs():
        try:
            p = load_pack(pid)
            print(f"{p.id:<16} v{p.version:<8} {p.content_hash[:12]}  {p.title}  scopes={','.join(p.allowed_scopes)}"
                  f"{'  ONLINE' if p.online else ''}")
        except ValueError as exc:
            print(f"{pid:<16} INVALID: {exc}")
    return 0


def _netcheck(quiet: bool = False) -> int:
    targets = [("1.1.1.1", 443), ("huggingface.co", 443), ("pypi.org", 443)]
    reachable = []
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=3):
                reachable.append(host)
        except OSError:
            pass
    if not quiet:
        for host, _ in targets:
            print(f"  {host:<16} {'REACHABLE' if host in reachable else 'blocked'}")
        print(f"Python: {sys.executable}")
        print("RESULT: offline (pass)" if not reachable else "RESULT: network reachable (fail)")
    return 0 if not reachable else 1


def cmd_netcheck(a: argparse.Namespace) -> int:
    return _netcheck()


def cmd_verify_log(a: argparse.Namespace) -> int:
    from .governor.intent_log import load_or_create_log_key, verify_log, verify_seal
    ok, n, _, problem = verify_log(a.path)
    print(f"chain: {'OK' if ok else 'BROKEN'} ({n} records){'' if ok else ' - ' + problem}")
    if not ok:
        return 1
    sok, sproblem = verify_seal(a.path, load_or_create_log_key())
    print(f"seal:  {'OK' if sok else 'NOT VERIFIED'}{'' if sok else ' - ' + sproblem}")
    return 0 if sok else 1


def cmd_stop(a: argparse.Namespace) -> int:
    s = load_settings(a.config, a.profile)
    Path(s.stop_file).touch()
    print(f"Created {s.stop_file}: the Governor halts within one tick. Delete it before the next session.")
    return 0


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="powder_ranger")
    ap.add_argument("--config", help="settings YAML (default: config/default.yaml)")
    ap.add_argument("--profile", help="player profile YAML")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("governor")
    g.add_argument("--process", required=True, help="target game executable, e.g. supertuxkart.exe")
    g.add_argument("--output", choices=["x360", "ds4", "dryrun"])
    g.add_argument("--pack", help="Game Pack folder (logged with its hash)")
    g.add_argument("--online", action="store_true", help="online-mode rules")
    g.set_defaults(fn=cmd_governor)

    r = sub.add_parser("reflex")
    r.add_argument("--process", required=True)
    r.add_argument("--delegation", required=True)
    r.add_argument("--port", type=int, default=5555)
    r.set_defaults(fn=cmd_reflex)

    la = sub.add_parser("launch")
    la.add_argument("--pack", help="Game Pack id or folder (sets process, output, allowed scopes)")
    la.add_argument("--start-game", action="store_true", help="start the game from the pack's launch settings")
    la.add_argument("--process")
    la.add_argument("--output", choices=["x360", "ds4", "dryrun"])
    la.add_argument("--delegate", default="full_autopilot", help="scope the player grants")
    la.add_argument("--port", type=int, default=5555, help="NitroGen server port")
    la.add_argument("--require-offline", action="store_true", help="refuse to start if the network is reachable")
    la.add_argument("--player-input", choices=["xinput", "keyboard", "gaze", "none"], default="none",
                    help="player's own controls; they always outrank the companion")
    la.add_argument("--player-slot", type=int, help="XInput slot of the physical pad (default: auto)")
    la.add_argument("--steady", action="store_true", help="smooth the player's sticks (tremor filter)")
    la.add_argument("--voice", action="store_true", help="start local voice commands (stop, you play, my turn)")
    la.set_defaults(fn=cmd_launch)

    pt = sub.add_parser("padtest")
    pt.add_argument("--output", choices=["x360", "ds4", "dryrun"])
    pt.add_argument("--hold", type=float, default=1.5, help="seconds per step")
    pt.set_defaults(fn=cmd_padtest)

    pl = sub.add_parser("player")
    pl.add_argument("--source", choices=["xinput", "keyboard", "gaze"], required=True)
    pl.add_argument("--gaze-cal", default="config/profiles/local_gaze.json")
    pl.add_argument("--face-model", default="models/face_landmarker.task")
    pl.add_argument("--slot", type=int)
    pl.add_argument("--steady", action="store_true")
    pl.set_defaults(fn=cmd_player)

    vo = sub.add_parser("voice")
    vo.add_argument("--model", default="base.en", help="faster-whisper model name or local path")
    vo.add_argument("--no-tts", action="store_true", help="print replies instead of speaking")
    vo.set_defaults(fn=cmd_voice)

    ca = sub.add_parser("calibrate")
    ca.add_argument("action", choices=["record", "fit", "reaction"])
    ca.add_argument("--trials", type=int, default=20)
    ca.add_argument("--file", help="recording path (record: output, fit: input)")
    ca.add_argument("--seconds", type=float, default=180)
    ca.add_argument("--slot", type=int)
    ca.add_argument("--name", help="profile name for fit")
    ca.set_defaults(fn=cmd_calibrate)

    gc = sub.add_parser("gaze-calibrate")
    gc.add_argument("--face-model", default="models/face_landmarker.task")
    gc.add_argument("--out", default="config/profiles/local_gaze.json")
    gc.set_defaults(fn=cmd_gaze_calibrate)

    sub.add_parser("packs").set_defaults(fn=cmd_packs)

    rp = sub.add_parser("report")
    rp.add_argument("path", nargs="?", help="session log (default: newest)")
    rp.add_argument("--metrics", help="reflex_metrics.csv (default: next to the log)")
    rp.set_defaults(fn=cmd_report)
    sub.add_parser("netcheck").set_defaults(fn=cmd_netcheck)

    v = sub.add_parser("verify-log")
    v.add_argument("path")
    v.set_defaults(fn=cmd_verify_log)

    sub.add_parser("stop").set_defaults(fn=cmd_stop)

    a = ap.parse_args(argv)     # --config / --profile go before the command
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
