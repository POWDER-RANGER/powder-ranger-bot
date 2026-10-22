"""Spoken command parsing: text -> structured player command.

Word-level matching, never substrings (the original prototype paused when it
heard "don't stop"). Negation flips or cancels a command. The kill words are
checked first and are deliberately easy to trigger: a false stop costs a
second, a missed stop can cost the player control.

Grammar for squad-style direction: VERB [TARGET] [MANNER]
    "move to the tower silent"   -> Command("move", target="tower", manner="silent")
    "go loud"                    -> Command("set_style", manner="loud")
    "you drive" / "take over"    -> Command("delegate", scope=...)
    "my turn" / "I've got it"    -> Command("revoke")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STOP_WORDS = {"stop", "halt", "freeze", "abort", "kill"}
NEGATIONS = {"don't", "dont", "do not", "never", "not"}
FILLERS = {"the", "a", "an", "to", "please", "now", "uh", "um", "okay", "ok", "hey", "companion", "ranger"}

MANNERS = {
    "silent": "silent", "silently": "silent", "quiet": "silent", "quietly": "silent", "stealthy": "silent",
    "sneaky": "silent", "loud": "loud", "aggressive": "loud", "fast": "fast", "quick": "fast",
    "quickly": "fast", "careful": "careful", "carefully": "careful", "slow": "careful", "slowly": "careful",
}

# phrase -> (verb, extra fields). Longest phrases are matched first.
PHRASES: dict[str, tuple[str, dict]] = {
    "resume": ("resume", {}),
    "keep going": ("resume", {}),
    "carry on": ("resume", {}),
    "you play": ("delegate", {"scope": "full_autopilot"}),
    "you take it": ("delegate", {"scope": "full_autopilot"}),
    "take over": ("delegate", {"scope": "full_autopilot"}),
    "autopilot": ("delegate", {"scope": "full_autopilot"}),
    "you drive": ("delegate", {"scope": "driving"}),
    "take the wheel": ("delegate", {"scope": "driving"}),
    "handle the small stuff": ("delegate", {"scope": "routine"}),
    "my turn": ("revoke", {}),
    "i've got it": ("revoke", {}),
    "i got it": ("revoke", {}),
    "let me play": ("revoke", {}),
    "give it back": ("revoke", {}),
    "status": ("status", {}),
    "what can i do": ("help", {}),
    "what can i do here": ("help", {}),
    "help": ("help", {}),
    "hold": ("hold", {}),
    "wait": ("hold", {}),
    "hold position": ("hold", {}),
    "follow": ("follow", {}),
    "flank left": ("flank", {"target": "left"}),
    "flank right": ("flank", {"target": "right"}),
    "go loud": ("set_style", {"manner": "loud"}),
    "go silent": ("set_style", {"manner": "silent"}),
    "stay hidden": ("set_style", {"manner": "silent"}),
    "be careful": ("set_style", {"manner": "careful"}),
    "make noise": ("distract", {}),
    "distract": ("distract", {}),
    "jump": ("press", {"button": "SOUTH"}),
}
MOVE_VERBS = {"move", "go", "head", "run", "walk", "sneak", "drive"}


@dataclass(frozen=True)
class Command:
    verb: str
    target: str | None = None
    manner: str | None = None
    scope: str | None = None
    button: str | None = None
    text: str = ""
    extras: dict = field(default_factory=dict, compare=False)


def _words(text: str) -> list[str]:
    t = text.lower().replace("’", "'")
    t = re.sub(r"do not", "don't", t)
    return re.findall(r"[a-z']+", t)


def _negated(words: list[str], i: int) -> bool:
    """True when one of the two words before position i is a negation."""
    return any(w in NEGATIONS for w in words[max(0, i - 2):i])


def parse(text: str) -> Command | None:
    words = _words(text)
    if not words:
        return None

    # 1. Kill words first, word-level, with negation check.
    for i, w in enumerate(words):
        if w in STOP_WORDS and not _negated(words, i):
            return Command("stop", text=text)

    joined = " " + " ".join(words) + " "

    # 2. Fixed phrases, longest first.
    for phrase in sorted(PHRASES, key=len, reverse=True):
        idx = joined.find(" " + phrase + " ")
        if idx < 0:
            continue
        start_word = joined[:idx].count(" ")
        if _negated(words, start_word):
            verb, extra = PHRASES[phrase]
            if verb == "resume":          # "don't keep going" == hold
                return Command("hold", text=text)
            return None                   # other negated commands are ignored
        verb, extra = PHRASES[phrase]
        return Command(verb, text=text, **extra)

    # 3. Movement: VERB [to] TARGET... [MANNER]
    if words[0] in MOVE_VERBS:
        manner = next((MANNERS[w] for w in words[1:] if w in MANNERS), None)
        target_words = [w for w in words[1:] if w not in FILLERS and w not in MANNERS]
        target = " ".join(target_words) or None
        return Command("move", target=target, manner=manner, text=text)

    return None
