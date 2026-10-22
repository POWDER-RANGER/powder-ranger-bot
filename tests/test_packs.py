import pytest

from powder_ranger.packs import list_packs, load_pack


def write(folder, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pack.yaml").write_text(text)
    return folder


def test_bundled_supertuxkart_pack_is_valid():
    assert "supertuxkart" in list_packs()
    p = load_pack("supertuxkart")
    assert p.process == "supertuxkart.exe" and not p.online
    assert "-N" in p.launch_args and len(p.content_hash) == 64


def test_hash_changes_with_content(tmp_path):
    f = write(tmp_path / "g", "id: g\nversion: 1\ntitle: G\nprocess: g.exe\n")
    h1 = load_pack(f).content_hash
    (f / "notes.md").write_text("tip")
    assert load_pack(f).content_hash != h1


@pytest.mark.parametrize("text,msg", [
    ("version: 1\ntitle: G\nprocess: g.exe\n", "missing 'id'"),
    ("id: other\nversion: 1\ntitle: G\nprocess: g.exe\n", "must match folder"),
    ("id: g\nversion: 1\ntitle: G\nprocess: g.exe\noutput: keyboard\n", "output must be"),
    ("id: g\nversion: 1\ntitle: G\nprocess: g.exe\nallowed_scopes: [godmode]\n", "unknown scopes"),
    ("id: g\nversion: 1\ntitle: G\nprocess: g.exe\nonline: true\nallowed_scopes: [full_autopilot]\n",
     "online game cannot allow full_autopilot"),
])
def test_invalid_packs_refused(tmp_path, text, msg):
    with pytest.raises(ValueError, match=msg):
        load_pack(write(tmp_path / "g", text))


def test_launch_refuses_scope_the_pack_does_not_allow(tmp_path, capsys):
    from powder_ranger.cli import main
    f = write(tmp_path / "g", "id: g\nversion: 1\ntitle: G\nprocess: g.exe\nallowed_scopes: [driving]\n")
    assert main(["launch", "--pack", str(f), "--delegate", "full_autopilot", "--output", "dryrun"]) == 4
    assert "does not allow 'full_autopilot'" in capsys.readouterr().out
