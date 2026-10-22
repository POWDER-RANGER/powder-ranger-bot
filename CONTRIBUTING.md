# Contributing

The project is early and small. Field reports from real hardware are the most useful contribution right now.

## Ground rules
- The player stays in charge. Changes that weaken the Governor's rules, the kill switch, the human-limit motor model or the sealed log need a written reason in the pull request.
- No game memory access, no code injection, nothing that makes the companion faster or more precise than a person.
- Play mode stays local. Network use belongs in prep steps only.
- Do not add personal data about any player to the repository, docs or tests.

## Before opening a pull request
```
pip install -e ".[dev]"
python -m pytest -q
ruff check .
```
Add a test for any behavior you change. Safety rules live in `powder_ranger/governor/policy.py`; each one has a test in `tests/`.

## Reporting a vulnerability
Use a private security advisory, as described in [SECURITY.md](SECURITY.md).
