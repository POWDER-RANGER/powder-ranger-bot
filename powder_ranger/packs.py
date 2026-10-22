"""Game Packs: everything game-specific, versioned and hashed.

A pack is a folder under packs/<id>/ with pack.yaml (and later: perception
templates, skills, knowledge notes). The core never changes per game; the
pack does. Every session logs the pack id, version and content hash, so a
result can always be traced to the exact pack that produced it.

pack.yaml fields:
  id, version, title       identity
  process                  game executable name (focus check, capture)
  launch.exe / launch.args optional: how to start the game for a session
  launch.ready_after_s     seconds to wait after starting it
  output                   x360 | ds4  (which virtual pad the game expects)
  reflex                   nitrogen | none
  online                   true if the game is played online (enables online-mode rules)
  allowed_scopes           delegations a player may grant for this game
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import ROOT

PACKS_DIR = ROOT / "packs"
KNOWN_SCOPES = {"full_autopilot", "driving", "routine", "combat"}


@dataclass(frozen=True)
class GamePack:
    id: str
    version: str
    title: str
    process: str
    path: Path
    content_hash: str
    output: str = "x360"
    reflex: str = "nitrogen"
    online: bool = False
    allowed_scopes: tuple[str, ...] = ("full_autopilot",)
    launch_exe: str | None = None
    launch_args: tuple[str, ...] = ()
    ready_after_s: float = 15.0
    extra: dict = field(default_factory=dict, compare=False)

    def session_info(self) -> dict:
        return {"pack_id": self.id, "pack_version": self.version, "pack_hash": self.content_hash}


def pack_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(f.relative_to(folder).as_posix().encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def load_pack(pack: str | Path) -> GamePack:
    folder = Path(pack)
    if not folder.exists():
        folder = PACKS_DIR / str(pack)
    spec_path = folder / "pack.yaml"
    if not spec_path.exists():
        raise FileNotFoundError(f"no pack.yaml in {folder}")
    d = yaml.safe_load(spec_path.read_text()) or {}

    problems = []
    for key in ("id", "version", "title", "process"):
        if not d.get(key):
            problems.append(f"missing '{key}'")
    if d.get("id") and d["id"] != folder.name:
        problems.append(f"id '{d['id']}' must match folder name '{folder.name}'")
    output = d.get("output", "x360")
    if output not in ("x360", "ds4"):
        problems.append(f"output must be x360 or ds4, not {output}")
    scopes = tuple(d.get("allowed_scopes", ["full_autopilot"]))
    unknown = set(scopes) - KNOWN_SCOPES
    if unknown:
        problems.append(f"unknown scopes {sorted(unknown)}")
    online = bool(d.get("online", False))
    if online and "full_autopilot" in scopes:
        problems.append("an online game cannot allow full_autopilot")
    if problems:
        raise ValueError(f"invalid pack {folder.name}: " + "; ".join(problems))

    launch = d.get("launch") or {}
    known = {"id", "version", "title", "process", "output", "reflex", "online", "allowed_scopes", "launch"}
    return GamePack(
        id=d["id"], version=str(d["version"]), title=d["title"], process=d["process"],
        path=folder, content_hash=pack_hash(folder), output=output,
        reflex=d.get("reflex", "nitrogen"), online=online, allowed_scopes=scopes,
        launch_exe=launch.get("exe"), launch_args=tuple(str(a) for a in launch.get("args", [])),
        ready_after_s=float(launch.get("ready_after_s", 15)),
        extra={k: v for k, v in d.items() if k not in known},
    )


def list_packs() -> list[str]:
    return sorted(p.parent.name for p in PACKS_DIR.glob("*/pack.yaml"))
