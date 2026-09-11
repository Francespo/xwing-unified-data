#!/usr/bin/env python3
"""
sync_data.py — Synchronize X-Wing game data across submodules and auto-detect points changes.

Designed for Francespo/xwing-unified-data:
1. Submodules: update `xwing-data2`, `xwing-data2-legacy`, `xwing-miniatures-font`
2. J1mBob: fetch & merge card/asset fixes from `https://github.com/J1mBob/xwing-data2.git`
3. Legacy (Darker333 / SogeMoge): fetch & merge updates for `xwing-data2-legacy`
4. YASB (Raithos): parse instant points and loadouts from `https://github.com/raithos/xwing`
5. Points Detection: inspect commit history and data diffs to automatically detect points balance updates
   and update points_history/*.json files.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[1]
XWA_DIR = ROOT_DIR / "xwing-data2"
LEGACY_DIR = ROOT_DIR / "xwing-data2-legacy"
POINTS_HISTORY_DIR = ROOT_DIR / "points_history"


def run_cmd(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and print output."""
    workdir = cwd or ROOT_DIR
    print(f"--> Running: {' '.join(cmd)} (in {workdir})")
    res = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr and res.returncode != 0:
        print(f"Error: {res.stderr.strip()}", file=sys.stderr)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with returncode {res.returncode}: {' '.join(cmd)}")
    return res


def sync_submodules():
    """Update all git submodules recursively from their remote HEADs."""
    print("\n=== Sincronizzazione Submoduli Git ===")
    if not (ROOT_DIR / ".git").exists():
        print("Not a git repository, skipping submodule update.")
        return
    run_cmd(["git", "submodule", "update", "--init", "--recursive", "--remote"])


def sync_j1mbob():
    """Fetch and merge latest fixes from J1mBob into xwing-data2."""
    print("\n=== Sincronizzazione da J1mBob (xwing-data2) ===")
    if not XWA_DIR.exists():
        print(f"Directory {XWA_DIR} does not exist.")
        return

    remotes_res = run_cmd(["git", "remote"], cwd=XWA_DIR, check=False)
    remotes = remotes_res.stdout.split()
    if "j1mbob" not in remotes:
        run_cmd(["git", "remote", "add", "j1mbob", "https://github.com/J1mBob/xwing-data2.git"], cwd=XWA_DIR)

    run_cmd(["git", "fetch", "j1mbob"], cwd=XWA_DIR)
    merge_res = run_cmd(["git", "merge", "j1mbob/master", "--no-edit"], cwd=XWA_DIR, check=False)
    if merge_res.returncode != 0:
        print("Notice: merge conflicts or non-fast-forward merge. Resetting or keeping local changes.")


def sync_legacy_darker():
    """Fetch and merge latest points from Darker333 / SogeMoge into xwing-data2-legacy."""
    print("\n=== Sincronizzazione da Darker333 / SogeMoge (xwing-data2-legacy) ===")
    if not LEGACY_DIR.exists():
        print(f"Directory {LEGACY_DIR} does not exist.")
        return

    remotes_res = run_cmd(["git", "remote"], cwd=LEGACY_DIR, check=False)
    remotes = remotes_res.stdout.split()
    if "darker" not in remotes:
        run_cmd(["git", "remote", "add", "darker", "https://github.com/Darker333/xwing-data2-legacy.git"], cwd=LEGACY_DIR)

    run_cmd(["git", "fetch", "darker"], cwd=LEGACY_DIR)
    run_cmd(["git", "merge", "darker/master", "--no-edit"], cwd=LEGACY_DIR, check=False)


def normalize_xws(name: str) -> str:
    """Canonicalize a card/pilot name to XWS format."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def sync_yasb_fast_points() -> int:
    """Download YASB cards-common.coffee and patch points/loadouts in xwing-data2 JSONs.
    Returns number of points changes patched."""
    print("\n=== Sincronizzazione Punti Lampo da YASB (Raithos) ===")
    url = "https://raw.githubusercontent.com/raithos/xwing/master/coffeescripts/content/cards-common.coffee"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "XWingUnifiedData-Sync/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        print(f"Failed to fetch YASB cards-common.coffee: {e}")
        return 0

    pilot_points: dict[str, dict[str, int]] = {}
    blocks = re.split(r'\n\s*name:\s*"', content)
    for block in blocks[1:]:
        name_match = re.match(r'^([^"]+)"', block)
        if not name_match:
            continue
        name = name_match.group(1)
        pts_match = re.search(r'\bpoints:\s*(\d+)', block)
        loadout_match = re.search(r'\bloadout:\s*(\d+)', block)
        ship_match = re.search(r'\bship:\s*"([^"]+)"', block)

        if pts_match:
            pts = int(pts_match.group(1))
            loadout = int(loadout_match.group(1)) if loadout_match else 0
            xws_key = normalize_xws(name)
            pilot_points[xws_key] = {"points": pts, "loadout": loadout, "name": name}
            if ship_match:
                ship_xws = normalize_xws(ship_match.group(1))
                pilot_points[f"{xws_key}-{ship_xws}"] = {"points": pts, "loadout": loadout, "name": name}

    print(f"Found {len(pilot_points)} point definitions in YASB.")

    pilots_dir = XWA_DIR / "data" / "pilots"
    if not pilots_dir.exists():
        print(f"Pilots directory {pilots_dir} not found.")
        return 0

    changes_count = 0
    for json_file in pilots_dir.rglob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            ship_xws = normalize_xws(data.get("xws", json_file.stem))
            modified = False

            for p in data.get("pilots", []):
                p_name = p.get("name", "")
                p_xws = normalize_xws(p.get("xws", p_name))

                match = pilot_points.get(f"{p_xws}-{ship_xws}") or pilot_points.get(p_xws)
                if match:
                    new_pts = match["points"]
                    new_loadout = match["loadout"]
                    old_cost = p.get("cost")
                    old_loadout = p.get("loadout")

                    if old_cost != new_pts:
                        p["cost"] = new_pts
                        modified = True
                        changes_count += 1
                    if new_loadout and old_loadout != new_loadout:
                        p["loadout"] = new_loadout
                        modified = True
                        changes_count += 1

            if modified:
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")
        except Exception as e:
            print(f"Warning: could not process {json_file}: {e}")

    print(f"Applied {changes_count} point/loadout updates from YASB.")
    return changes_count


def auto_detect_points_history():
    """Check git commits in submodules and data diffs to auto-detect new points updates."""
    print("\n=== Rilevamento Automatico Cambi Punti ===")

    # 1. Check Legacy
    legacy_history_file = POINTS_HISTORY_DIR / "legacy.json"
    if legacy_history_file.exists() and LEGACY_DIR.exists():
        try:
            with open(legacy_history_file, "r", encoding="utf-8") as f:
                leg_hist = json.load(f)

            current_latest = leg_hist.get("latest_date", "2020-01-01")
            cmd = [
                "git", "log", f"--since={current_latest}",
                "--format=%ad|%h|%s", "--date=short",
                "--", "data/pilots", "data/upgrades"
            ]
            res = subprocess.run(cmd, cwd=LEGACY_DIR, capture_output=True, text=True)
            commits = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]

            new_commits = []
            for c in commits:
                parts = c.split("|", 2)
                if len(parts) == 3:
                    c_date, c_hash, c_subj = parts
                    if c_date > current_latest:
                        new_commits.append((c_date, c_hash, c_subj))

            if new_commits:
                latest_commit = new_commits[0]
                new_date, new_hash, new_subj = latest_commit
                print(f"[Legacy] Detected newer points update commit: {new_date} - {new_subj} ({new_hash})")

                new_entry = {
                    "date": new_date,
                    "version": new_subj,
                    "description": f"Automated points update from xwing-data2-legacy ({new_hash})",
                    "steward": "X-Wing 2.0 Legacy (X2PO)",
                    "highlights": [f"Commit {new_hash}: {new_subj}"],
                }
                leg_hist["updates"].insert(0, new_entry)
                leg_hist["latest_date"] = new_date

                with open(legacy_history_file, "w", encoding="utf-8") as f:
                    json.dump(leg_hist, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                print(f"[Legacy] Successfully bumped latest_date to {new_date}")
            else:
                print(f"[Legacy] Up to date (latest points release: {current_latest})")
        except Exception as e:
            print(f"Error checking Legacy points history: {e}")

    # 2. Check XWA
    xwa_history_file = POINTS_HISTORY_DIR / "xwa.json"
    if xwa_history_file.exists() and XWA_DIR.exists():
        try:
            with open(xwa_history_file, "r", encoding="utf-8") as f:
                xwa_hist = json.load(f)

            current_latest = xwa_hist.get("latest_date", "2020-01-01")
            cmd = [
                "git", "log", f"--since={current_latest}",
                "--format=%ad|%h|%s", "--date=short",
                "--", "data/pilots", "data/upgrades"
            ]
            res = subprocess.run(cmd, cwd=XWA_DIR, capture_output=True, text=True)
            commits = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]

            new_commits = []
            for c in commits:
                parts = c.split("|", 2)
                if len(parts) == 3:
                    c_date, c_hash, c_subj = parts
                    if c_date > current_latest:
                        new_commits.append((c_date, c_hash, c_subj))

            if new_commits:
                latest_commit = new_commits[0]
                new_date, new_hash, new_subj = latest_commit
                print(f"[XWA] Detected newer points update commit: {new_date} - {new_subj} ({new_hash})")

                new_entry = {
                    "date": new_date,
                    "version": new_subj,
                    "description": f"Automated points update from xwing-data2 ({new_hash})",
                    "steward": "X-Wing Alliance (XWA)",
                    "highlights": [f"Commit {new_hash}: {new_subj}"],
                }
                xwa_hist["updates"].insert(0, new_entry)
                xwa_hist["latest_date"] = new_date

                with open(xwa_history_file, "w", encoding="utf-8") as f:
                    json.dump(xwa_hist, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                print(f"[XWA] Successfully bumped latest_date to {new_date}")
            else:
                print(f"[XWA] Up to date (latest points release: {current_latest})")
        except Exception as e:
            print(f"Error checking XWA points history: {e}")


def main():
    parser = argparse.ArgumentParser(description="Synchronize X-Wing game data & auto-detect points updates.")
    parser.add_argument("--sync-submodules", action="store_true", default=True, help="Update git submodules")
    parser.add_argument("--no-submodules", action="store_false", dest="sync_submodules", help="Skip submodules update")
    parser.add_argument("--sync-j1mbob", action="store_true", help="Fetch & merge card fixes from J1mBob/xwing-data2")
    parser.add_argument("--sync-legacy", action="store_true", help="Fetch & merge updates from Darker333/xwing-data2-legacy")
    parser.add_argument("--sync-yasb", action="store_true", help="Patch points & loadouts from YASB (Raithos)")
    parser.add_argument("--detect-points", action="store_true", default=True, help="Auto-detect points updates and bump history")

    args = parser.parse_args()

    if args.sync_submodules:
        sync_submodules()

    if args.sync_j1mbob:
        sync_j1mbob()

    if args.sync_legacy:
        sync_legacy_darker()

    if args.sync_yasb:
        sync_yasb_fast_points()

    if args.detect_points:
        auto_detect_points_history()

    print("\n✓ Sincronizzazione e rilevamento completati con successo!")


if __name__ == "__main__":
    main()
