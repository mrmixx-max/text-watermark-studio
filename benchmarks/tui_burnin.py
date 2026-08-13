"""TUI burn-in: drive every menu action through a real test file and fail
loudly on any exception. Run before releases.

Usage: python benchmarks/tui_burnin.py [path-to-sample-file]

Needs the `tui` extra (textual). Runs headless via textual's test pilot.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.ui.tui import MENU, StudioTUI  # noqa: E402

SAMPLE = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/ai_sample_en.txt"

# actions that hit the network or spawn long benchmarks — exercised but
# with a short timeout so the burn-in stays bounded
SLOW_OR_NETWORK = {"update", "attack-matrix", "synthid-sweep"}


async def burn_in() -> int:
    failures: list[str] = []
    app = StudioTUI()
    # run in a throwaway cwd so actions that write outputs (report html,
    # file tools) never leave artifacts in the repo
    run_dir = Path(tempfile.mkdtemp(prefix="tws-burnin-cwd-"))
    old_cwd = Path.cwd()
    os.chdir(run_dir)
    try:
        async with app.run_test(size=(120, 36)) as pilot:
            for label, action_id in MENU:
                method = getattr(app, "action_" + action_id.replace("-", "_"), None)
                if method is None:
                    failures.append(f"{action_id}: missing method")
                    continue
                try:
                    if action_id == "watch-once":
                        app.query_one("#path").value = str(old_cwd / "tests" / "fixtures")
                    elif action_id in ("attack-matrix", "synthid-sweep", "update"):
                        app.query_one("#path").value = ""
                    else:
                        # run against a throwaway copy so file actions never
                        # write -clean/-signed artifacts next to tracked fixtures
                        src = old_cwd / SAMPLE
                        tmp_copy = run_dir / src.name
                        tmp_copy.write_bytes(src.read_bytes())
                        app.query_one("#path").value = str(tmp_copy)
                    await pilot.pause()
                    method()
                    await pilot.pause()
                    print(f"  OK   {label}")
                except Exception as e:
                    failures.append(f"{action_id}: {type(e).__name__}: {e}")
                    print(f"  FAIL {label}: {type(e).__name__}: {e}")
                    traceback.print_exc(limit=3)
    finally:
        os.chdir(old_cwd)

    print(f"\n{len(MENU) - len(failures)}/{len(MENU)} Aktionen fehlerfrei.")
    if failures:
        print("\nFehlgeschlagen:")
        for f in failures:
            print(" -", f)
        return 1
    print("BURN-IN PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(burn_in()))
