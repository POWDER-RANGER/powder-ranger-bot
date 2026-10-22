# History

`original_mgsv_prototype/` holds the first version of this project, written
years before the current design. The files are kept byte-for-byte as they
were; `SHA256SUMS` records their hashes as of 2026-10-21.

They are a record, not a codebase: nothing here is imported or run.

## What carried forward
Assistance levels, input methods (eye, voice, blink, switch, BCI, hybrid),
the accessibility profile, the voice command vocabulary, spoken status and
alerts, human timing variation and rate limits, scancode input with no DLL
injection, local-only processing, and testing with disabled players.

## What was retired, and why
- Memory reading (Cheat Engine tables, unsourced offsets): the companion
  perceives the screen only.
- Placeholders that printed success without doing the work: status reports
  must be true.
- Accessibility mode never started the main loop.
- Player commands bypassed rate limits, and two input paths could drive the
  controller at once: the Governor is now the single path.
- Blink confirm fired whenever eye detection missed; gaze came from an eye
  bounding box; enemies were found with a human-face detector.
- Substring command matching ("don't stop" paused the AI).
- An LLM consulted every frame.
- The roadmap in `mgsv_autonomous_assistant_architecture.txt` marks phases
  complete ([x]). They were planned, not built.
