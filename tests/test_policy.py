from powder_ranger.governor.policy import GovernorConfig, GovernorPolicy
from powder_ranger.intent import Delegation, GamepadFrame, IntentPacket, Source

NOW = 1000.0


def pkt(seq, source=Source.REFLEX, created=NOW, ttl=250, conf=1.0, deleg="d1", frames=None):
    return IntentPacket(seq=seq, source=source, created_at=created, ttl_ms=ttl,
                        frames=frames or (GamepadFrame(lx=0.5),), confidence=conf, delegation_id=deleg)


def policy(**kw):
    p = GovernorPolicy(GovernorConfig(**kw))
    p.grant(Delegation(id="d1", scope="full_autopilot", granted_at=NOW))
    return p


def test_allows_delegated_companion_output():
    d = policy().evaluate(pkt(1), NOW, focused=True)
    assert d.allow and "delegation 'd1'" in d.reasons[0]


def test_halt_denies_everything_including_player():
    p = policy()
    p.halt("test")
    assert not p.evaluate(pkt(1), NOW, True).allow
    assert not p.evaluate(pkt(2, source=Source.PLAYER, deleg=None), NOW, True).allow


def test_stale_packet_denied():
    d = policy().evaluate(pkt(1, created=NOW - 0.3, ttl=250), NOW, True)
    assert not d.allow and "stale" in d.reasons[0]


def test_replay_and_out_of_order_denied():
    p = policy()
    assert p.evaluate(pkt(5), NOW, True).allow
    assert not p.evaluate(pkt(5), NOW + 0.1, True).allow
    assert not p.evaluate(pkt(4), NOW + 0.2, True).allow


def test_player_input_allowed_without_delegation_or_focus():
    p = GovernorPolicy(GovernorConfig())
    assert p.evaluate(pkt(1, source=Source.PLAYER, deleg=None), NOW, focused=False).allow


def test_player_override_preempts_companion_then_expires():
    p = policy(player_override_hold_ms=1500)
    assert p.evaluate(pkt(1, source=Source.PLAYER, deleg=None), NOW, True).allow
    d = p.evaluate(pkt(2, created=NOW + 1.0), NOW + 1.0, True)
    assert not d.allow and "player override" in d.reasons[0]
    assert p.evaluate(pkt(3, created=NOW + 1.6), NOW + 1.6, True).allow


def test_companion_needs_active_delegation():
    p = GovernorPolicy(GovernorConfig())
    d = p.evaluate(pkt(1, deleg=None), NOW, True)
    assert not d.allow and "no delegation" in d.reasons[0]
    p.grant(Delegation(id="short", scope="driving", granted_at=NOW, expires_at=NOW + 1))
    assert p.evaluate(pkt(2, deleg="short", created=NOW + 0.5), NOW + 0.5, True).allow
    d = p.evaluate(pkt(3, deleg="short", created=NOW + 2), NOW + 2, True)
    assert not d.allow and "expired" in d.reasons[0]


def test_revoke_stops_companion():
    p = policy()
    p.revoke()
    assert not p.evaluate(pkt(1), NOW, True).allow


def test_online_mode_refuses_autopilot_grant_and_requires_presence():
    p = GovernorPolicy(GovernorConfig(online_mode=True, presence_timeout_s=20))
    assert p.grant(Delegation(id="a", scope="full_autopilot", granted_at=NOW))  # refused
    assert not p.grant(Delegation(id="r", scope="routine", granted_at=NOW))
    d = p.evaluate(pkt(1, deleg="r"), NOW, True)
    assert not d.allow and "not present" in d.reasons[0]
    p.note_presence(NOW)
    assert p.evaluate(pkt(2, deleg="r", created=NOW + 5), NOW + 5, True).allow
    d = p.evaluate(pkt(3, deleg="r", created=NOW + 30), NOW + 30, True)
    assert not d.allow and "not present" in d.reasons[0]


def test_focus_loss_denies_companion():
    d = policy().evaluate(pkt(1), NOW, focused=False)
    assert not d.allow and "not in front" in d.reasons[0]


def test_confidence_floor():
    d = policy(confidence_floor=0.6).evaluate(pkt(1, conf=0.4), NOW, True)
    assert not d.allow and "confidence" in d.reasons[0]


def test_rate_limit():
    p = policy(max_packets_per_sec=4)        # burst of 1
    assert p.evaluate(pkt(1), NOW, True).allow
    assert not p.evaluate(pkt(2), NOW + 0.01, True).allow
    assert p.evaluate(pkt(3, created=NOW + 0.3), NOW + 0.3, True).allow


def test_menu_buttons_stripped_from_companion_only():
    frames = (GamepadFrame(buttons=frozenset({"START", "SOUTH"})),)
    d = policy().evaluate(pkt(1, frames=frames), NOW, True)
    assert d.allow and d.packet.frames[0].buttons == frozenset({"SOUTH"})
    d = policy().evaluate(pkt(1, source=Source.PLAYER, deleg=None, frames=frames), NOW, True)
    assert "START" in d.packet.frames[0].buttons
