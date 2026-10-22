# Game Packs

One folder per game: `packs/<id>/pack.yaml`, plus (in later stages) perception
templates, a skill library and knowledge notes. The pack's content hash is
logged with every session, so results trace to the exact pack used.

Rules checked at load: required fields, id matches the folder, known
delegation scopes only, and an online game cannot allow full_autopilot.

`python -m powder_ranger packs` lists installed packs and their hashes.
