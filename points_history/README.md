# Star Wars: X-Wing Points Change History

This directory contains the historical record of official and community points balance updates for *Star Wars: X-Wing Miniatures Game*.

## Systems Supported

1. **`legacy.json` — X-Wing 2.0 Legacy (X2PO)**
   - Classic 200-point dogfight system maintained by the X2PO community.
   - Latest update: `2026-09-26` (September 2026 Points Update).
   - Website: [https://x2po.org](https://x2po.org) | Points portal: [https://points.x2po.org](https://points.x2po.org).

2. **`xwa.json` — X-Wing Alliance (XWA)**
   - Scenario/objective system continuing 2.5 with modern 50-point balancing.
   - Latest update: `2026-10-11` (50P 2.1.1 Hotfix).
   - Website: [https://xwing.life](https://xwing.life) | Points portal: [https://www.xwing.life/points](https://www.xwing.life/points).

3. **`amg.json` — Atomic Mass Games (AMG 2.5)**
   - Official 2.5 ruleset archive (20 squad points + Loadout Values).
   - Final update: `2024-09-06` (Final official print-and-play points drop).
   - Documents archive: [https://www.atomicmassgames.com/x-wing-documents](https://www.atomicmassgames.com/x-wing-documents).

4. **`ffg.json` — Fantasy Flight Games (FFG 2.0)**
   - Original Second Edition dynamic points balance history (2018–2020).
   - Final update: `2020-11-24` (2021 Season 1 Update before AMG transition).

## Usage in M3tacron

- The dashboard time-range filter defaults to **"Since last points change" (`points_update`)**, which automatically resolves to `latest_date` for the active ruleset (`Legacy` vs `XWA`).
- Other game modes anchor to these four core systems and do not have separate points changes.


## Automation

- `Francespo/xwing-data2` runs **Sync YASB points** daily at 04:30 UTC. It resolves the latest YASB points release commit, applies only that release's `points`/`loadout` diff, and commits `data: apply YASB 50P <version> points (<YYYY-MM-DD>)`.
- This repository's **Sync Game Data & Auto-detect Points** workflow updates the submodules and records the release in `points_history/*.json`.
- `Francespo/m3tacron` then opens the `chore/game-data-sync` PR and auto-merges it after CI.
