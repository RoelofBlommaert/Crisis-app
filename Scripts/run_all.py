"""
Run all data-gathering scripts in sequence and print a summary.

Usage:  python run_all.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    "fetch_gdelt_tension.py",
    "fetch_gdacs_events.py",
    "fetch_reliefweb_events.py",
    "fetch_cbs_travel.py",
    "fetch_opensky_snapshot.py",
]

SCRIPTS_DIR = Path(__file__).resolve().parent


def main() -> None:
    results = {}
    for script in SCRIPTS:
        print(f"\n{'=' * 60}\nRunning {script}\n{'=' * 60}")
        proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / script)])
        results[script] = proc.returncode

    print(f"\n{'=' * 60}\nSummary\n{'=' * 60}")
    for script, code in results.items():
        status = "OK" if code == 0 else f"FAILED (exit {code})"
        print(f"  {script}: {status}")


if __name__ == "__main__":
    main()
