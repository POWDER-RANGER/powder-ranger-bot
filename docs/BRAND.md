# Æther brand and visual baseline

Version 1, 2026-10-25. Values are read from the files named in each section. Lines marked **[proposed]** are not in any file yet. Lines marked **[gap]** are inconsistencies to decide.

## 1. Names

| Name | Role | Rule |
| --- | --- | --- |
| **Æther** | The platform and product | Display text always uses the ligature Æ: `ÆTHER` in caps, `Æther` in sentences. Plain `Aether` only in code paths and identifiers, e.g. `%USERPROFILE%\Aether`. |
| **PR-REX** | The companion: the body double the player directs | Name the companion PR-REX where it is the actor ("PR-REX proposes; the Governor decides"). Use "companion" in generic copy. |
| **POWDER-RANGER** | GitHub organization and the umbrella name of the first concept | Used in URLs and attribution only. Not a product name. |
| `powder_ranger`, `powder-ranger` | Python package and CLI | Unchanged. Renaming the code is a separate task. |

Taglines, in order of use:

- Site hero lead: **A local, accessibility-first game companion. The player directs. The companion plays.**
- Site quote, banner line, and og:description: **The player is the legend. The companion is the body double.**
- README and social preview: **The player directs. The companion plays.**
- Banner strapline (mono, uppercase): **LOCAL ONLY · HUMAN LIMITS · SIGNED · SEALED · PLAYER ALWAYS WINS**. The social preview uses the same line without the last clause.

**[gap]** The site footer still reads "Æther is part of Powder Ranger". It is kept as umbrella attribution. Decide whether Powder Ranger remains an umbrella or is retired.

## 2. Color

### Dark (default), site `:root` in `index.html`

| Token | Hex | Use |
| --- | --- | --- |
| `--bg` | `#150809` | Page background |
| `--panel` | `#2a1317` | Panel base |
| `--panel2` | `#37191f` | Panel top |
| `--line` | `#4a2a30` | Hairlines |
| `--seam` | `#080304` | 2px seams, hero bottom edge |
| `--hi` | `#7c464f` | Highlight edge on buttons |
| `--txt` | `#e9e3d9` | Body text |
| `--mut` | `#b3a6a0` | Secondary text |
| `--acc` | `#f2c230` | Safety yellow: accent, kicker square, hazard stripe, outline buttons |
| `--acc-ink` | `#150809` | Text on accent |
| `--hot` | `#c7303a` | Gradient start for primary button, rule bar. Not for text. |
| `--maroon` | `#6e1720` | Gradient end for primary button |
| `--ok` / `--warn` / `--bad` | `#86be93` / `#e3b04c` / `#ec7059` | Status |
| `--h1a` / `--h1b` / `--h1c` | `#f7f2ea` / `#c4bbb0` / `#7c736b` | Steel display gradient |
| `--glow` | `rgba(170,34,46,.30)` | Red glow |
| `--shade` | `rgba(0,0,0,.62)` | Shadows |

### Light (`prefers-color-scheme: light`)

| Token | Hex |
| --- | --- |
| `--bg` / `--panel` / `--panel2` | `#e2ddd4` / `#efebe3` / `#f6f2ea` |
| `--txt` / `--mut` | `#1d0f12` / `#5e4e4f` |
| `--acc` / `--acc-ink` | `#8a1c26` / `#ffffff` |
| `--hot` / `--maroon` | `#9d1f2b` / `#6e1720` |
| `--ok` / `--warn` / `--bad` | `#2c7442` / `#8a5a00` / `#a8321e` |

### Artwork palette (`assets/*.svg`)

| Role | Hex |
| --- | --- |
| Ink / plate black | `#0c0405` |
| Plate gradient (top to bottom) | `#3f0f16`, `#2a0a10`, `#170508` |
| Edge maroon (inner rule) | `#a24a52` at 50–60% |
| Glow | `#9a1f2a` at 40%, `#b0252f` at 0% |
| Steel wordmark (top to bottom) | `#f1ece4`, `#bdb5ab` (45%), `#7d756d` |
| Rivet | `#d8d0c6`, `#7d756d`, `#2a1a1c` |
| Bone text | `#efe9df` |
| Rose text (kicker, strapline) | `#d9a9ad`, `#c79da1` |
| Yellow | `#f2c230` |

**[gap]** Two dark bases exist. The site uses `#150809` and the artwork uses `#0c0405`. Pick one for both. Until then, do not mix them in one surface.

### Contrast (WCAG 2.x, computed)

| Pair | Ratio | Result |
| --- | --- | --- |
| Dark body `#e9e3d9` on `#150809` | 15.37 | AA and AAA |
| Dark muted `#b3a6a0` on `#150809` | 8.29 | AA and AAA |
| Dark muted on panel `#37191f` | 6.72 | AA |
| Dark accent `#f2c230` on `#150809` | 11.71 | AA and AAA |
| Accent-ink on accent | 11.71 | AA and AAA |
| White on primary button, hot end `#c7303a` | 5.37 | AA |
| White on primary button, maroon end `#6e1720` | 11.63 | AA and AAA |
| Dark `#c7303a` on `#150809` | 3.65 | **Fails for text.** Decorative only. |
| Light body `#1d0f12` on `#e2ddd4` | 13.75 | AA and AAA |
| Light muted `#5e4e4f` on `#e2ddd4` | 5.80 | AA |
| Light accent `#8a1c26` on `#e2ddd4` | 6.83 | AA |
| Light OK `#2c7442` on `#e2ddd4` | 4.21 | **Fails for small text.** |
| Artwork bone `#efe9df` on `#2a0a10` | 15.13 | AA and AAA |
| Artwork rose `#c79da1` on `#2a0a10` | 7.63 | AA and AAA |

Rule: text uses `--txt`, `--mut`, `--acc`, or the bone and rose tones. `--hot` is never a text color.

## 3. Typography

| Role | Face | Setting (from the site CSS) |
| --- | --- | --- |
| Display | Big Shoulders Display, subset woff2, OFL 1.1 (`assets/fonts/`) | H1: 800, `clamp(84px,17vw,190px)`, line-height .92, tracking .07em. H2: 800, `clamp(34px,5.4vw,56px)`, tracking .05em, uppercase. |
| Text | Helvetica Neue, Helvetica, Arial, system-ui | Body. Lead: `clamp(18px,2.4vw,26px)`. |
| Labels | ui-monospace, SF Mono, Menlo, Consolas, DejaVu Sans Mono | Uppercase. Kicker 12px/600, tracking .28em. Chip 11px, tracking .18em. Button 12px/700, tracking .2em. |

The wordmark `ÆTHER` is outlined Big Shoulders glyphs, not live text. Keep it outlined in every SVG.

## 4. Materials and motifs

- **Plate.** Dark maroon vertical gradient, plus a brushed texture (stretched fractal noise), grain, and a wear overlay at about 38% opacity, masked toward the edges.
- **Steel.** Bone-to-grey vertical gradient on the wordmark, with a plate-black offset shadow (about 4px, 5px, 70% opacity).
- **Rivets.** Radial shading, `#d8cfc5` to `#160a0c`. Placed at the corners and along the top and bottom edges of banners.
- **Hazard stripe.** 45° yellow and `#150809` bands, 14px per band, 12–22px tall, on the bottom edge of hero and banner panels.
- **Seams and edges.** 2px `--seam` between sections. 1px maroon inner rule at about 60%.
- **Corner brackets.** 18px yellow L-shapes at the top left of cards.
- **Reticle.** Concentric rings (radius 16, 56, 92, and a dashed 120) with four ticks, stroke `#f2c230` at 2.2px. The reticle is decorative. It is not a logo.
- **Dividers.** 150px bar, 5–6px tall. Yellow, or hot and yellow split 62/38.

## 5. Logo and lockups

- **Wordmark.** `ÆTHER`: outlined Big Shoulders, steel fill, plate-black shadow.
- **Mark.** The reticle, used alone or to the right of the wordmark.
- **Kicker lockup.** Yellow square, then `ÆTHER // FIELD COMPANION` in mono.
- **[proposed] Clear space.** One cap height of the Æ on every side.
- **[proposed] Minimum size.** Wordmark 160px wide on screen.
- **[gap]** The wordmark generator (`build_svgs.py`, which uses fontTools to outline the glyphs) lives in the scratchpad, not in the repo. Move it to `scripts/brand/` so the wordmark can be rebuilt.

## 6. Components (site)

- **Kicker** (`.kick`). Yellow square, then mono uppercase, muted.
- **Chip** (`.chip`). 1px yellow outline, mono 11px, transparent-dark fill.
- **Button** (`.btn`). 1px yellow outline, mono 12px/700.
- **Primary button** (`.btn.primary`). Gradient `--hot` to `--maroon`, white text, inset top highlight, drop shadow.
- **Card** (`.card`). Brushed panel gradient, 7px inner border line, yellow top-left bracket, muted paragraph text.
- **Rule** (`.hero .rule`). 150×6px, `--hot` 0–62%, `--acc` 62–100%.
- **Hero.** Wear overlay, 12px hazard strip at the bottom.

## 7. Voice

- Plain and literal. No hype, no superlatives.
- State only what `docs/VERIFICATION.md` records as run. The site already says so: "Nothing here is claimed before it has run."
- Name the player as the legend and the companion as the body double. Never describe the companion as the one in control.
- Use "companion" or PR-REX, not "bot", in product copy. The repo name is the only exception.
- Scope identifiers (`full_autopilot`, `driving`) are code. Do not use them as marketing words.

## 8. Asset inventory

| File | Size | Used by |
| --- | --- | --- |
| `index.html` | page | GitHub Pages site |
| `assets/banner.svg` | 1280×360 | README hero |
| `assets/social-preview.svg` / `.png` | 1280×640 | `og:image` (PNG) |
| `assets/architecture.svg` | | README and site, operating picture |
| `assets/aether-operating-path.svg` | | **Not referenced** by README or site |
| `assets/aether-with-the-legend.svg` | | **Not referenced** by README or site. Companion box is labeled PR-REX. |
| `assets/aether-learning.svg` | | **Not referenced** by README or site |
| `assets/fonts/BigShouldersDisplay-subset.woff2`, `OFL.txt` | | Site display face |

## 9. Changes in this baseline

- `ÆTHER // FIELD COMPANION` replaces `POWDER RANGER // FIELD COMPANION` in `banner.svg`, `social-preview.svg`, and `social-preview.png`.
- The site kicker is `ÆTHER // Field companion`.
- README names the companion: "The companion is **PR-REX**."
- The companion box in `aether-with-the-legend.svg` is labeled PR-REX. The title stays ÆTHER.

## 10. Open decisions

1. One dark base for site and artwork (`#150809` or `#0c0405`).
2. Whether Powder Ranger survives as the umbrella in the footer.
3. Move the wordmark generator into the repo.
4. Three diagrams (`aether-operating-path.svg`, `aether-with-the-legend.svg`, `aether-learning.svg`) are not linked anywhere. Link them from the site and README, or retire them.
