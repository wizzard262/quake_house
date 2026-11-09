# Quake Map - My House

A Quake (1996) map of my house that I built in 1997, now playable in the browser.

**Play:** https://wizzard262.github.io/quake_house/

Ported with Claude Code so the Quake map is rendered in the browser with JavaScript.

## What it does

- Walk round the house with Quake's own collision and movement (jumping, stairs, swimming)
- Doors, buttons, a lift, keys and locked rooms work as they did in Quake
- The map's own 1997 textures and baked lighting

## The level

**Goal: find the golden cup in the bathroom.**

- The silver key opens your bedroom (the door shows a silver key)
- The gold key (where the biosuit used to be) opens the downstairs cupboard (its doors show a gold key) and works the lift inside
- The bathroom is locked from the landing: take the lift to the loft and drop through the hole in the floor
- The bathroom door opens from inside, to get out

## Changes to the 1997 map

All made in the viewer (`MAP_MODS` in `viewer/viewer.html`); the `.bsp` files are untouched.

- A doorway from the loft onto the flat roof
- Keys: the gold key became the silver key; the biosuit became the gold key, needed for the cupboard and the lift
- Key doors shut again once unlocked (in Quake they stay open), so the bedroom door no longer stands up in the loft doorway
- The bathroom door opens only from inside
- The golden cup in the bathroom; picking it up ends the level and shows your time. `R` puts the keys and the cup back

Controls: click to play, mouse to look, W A S D to move, Space to jump, click to shoot buttons, N for noclip, R to restart.

## Technologies

- JavaScript, three.js (WebGL) and GLSL shaders
- Quake BSP collision hulls and player movement ported to JavaScript
- Python converter (`viewer/bsp2js.py`): geometry, textures decoded with the Quake palette, baked lightmaps, entities
- GitHub Pages

## Files

| File | What it is |
|------|------------|
| `beak8v.bsp` | The final version, 1 Nov 1997 (the one the viewer shows) |
| `beak.bsp`, `beak8t.bsp` | Earlier versions, 25 Oct 1997 |
| `house7gg.bsp`, `house7gi.bsp` | Early versions, 6 Oct 1997 |
| `2.bsp` | A test room, 18 Sep 1997 |
| `tests/` | Playwright test of the level |
| `viewer/` | The browser viewer and the converted map data (open an older one with `viewer/viewer.html?map=house7gi`) |

To rebuild the data after changing a map: `python viewer/bsp2js.py "*.bsp"` (from the repo root, Python 3, no packages needed).

## Tests

`tests/game.test.mjs` plays the level in a visible browser and checks the keys, locks, doors, the hole and the cup. From the repo root: `npm install` once, then `npm test` (add `-- --keep` to leave the window open).

## Credits

- Quake and its textures (embedded in the maps, as Quake maps always included them) are id Software's.
- `viewer/palette.lmp`, the standard Quake palette, from [OpenGameArt](https://opengameart.org/content/quake-i-palette-and-colormaps) (CC0).
