"""
Generate FICTIONAL, illustrative passport-application counts per tracked
country, for the last 10 years.

Why synthetic: real passport-application-per-post data is internal
BZ/RvIG consular data -- no public source exists for it (checked before
writing this script, not assumed). Per STRATEGY.md, sources without
confirmed real access get a clearly-labelled synthetic placeholder
instead of being silently skipped or faked as real.

This is deliberately a secondary, illustrative layer: `presence_signal`
(see merge_data.py) is still dominated by the real RNI count from
fetch_rni_nederlanders.py (up to 92 of 100 points), but as of
2026-09-15 this series' recent-vs-prior trend also feeds a small
(max +/-8 point) nudge on top -- an explicit, flagged exception to the
"synthetic never feeds a score" principle the rest of this app follows
(see the removed synthetic comms-volume layer from the earlier
data-minimization pass for why a synthetic-only signal, with no real
anchor at all, was judged not worth keeping). Because that nudge is
synthetic, presence_signal is now marked `is_partially_synthetic` in
the output and shown with an asterisk in the UI, with the real/
synthetic split (`presence_breakdown`) exposed rather than hidden.

Numbers here are deterministic (seeded per country, not random per run)
and loosely scaled off that country's real RNI-registered count (bigger
tracked community -> more plausible passport renewals/year), plus a
small year-over-year drift so the series isn't a flat line. Never to be
read as real BZ/consular figures.

Output:
  Data/Synthetic/passport_applications_<date>.csv
"""

import csv
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from countries import COUNTRIES

REPO_ROOT = Path(__file__).resolve().parent.parent
RNI_DIR = REPO_ROOT / "Data" / "RNI"
OUT_DIR = REPO_ROOT / "Data" / "Synthetic"

YEARS_BACK = 10
# A Dutch passport is valid for 10 years (adults), so a stable diaspora's
# RNI-registered population renews at a rough ~1-in-10 rate per year on
# average -- used only as a plausible illustrative anchor, not a claim.
ANNUAL_RENEWAL_SHARE = 0.10


def latest_rni_file() -> Path | None:
    matches = sorted(RNI_DIR.glob("rni_nederlanders_*.csv"))
    return matches[-1] if matches else None


def load_rni_counts() -> dict:
    path = latest_rni_file()
    counts = {}
    if not path:
        print("  ! no RNI file found -- run fetch_rni_nederlanders.py first")
        return counts
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            counts[row["country"]] = int(row["rni_registered"])
    print(f"  loaded RNI counts from {path.name}")
    return counts


def seeded_unit_value(country: str, year: int, salt: str) -> float:
    """Deterministic pseudo-random value in [0, 1), seeded by
    country+year+salt so re-running this script produces identical
    output (per STRATEGY.md's "deterministic, not random-per-run" rule
    for synthetic data)."""
    key = f"{country}:{year}:{salt}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def main() -> None:
    print("Loading real RNI counts to anchor the synthetic scale...")
    rni_counts = load_rni_counts()

    current_year = date.today().year
    years = list(range(current_year - YEARS_BACK + 1, current_year + 1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"passport_applications_{date.today().isoformat()}.csv"

    rows = []
    for c in COUNTRIES:
        name = c["name"]
        rni = rni_counts.get(name, 500)  # fallback anchor if RNI data missing
        base = max(10, round(rni * ANNUAL_RENEWAL_SHARE))

        for year in years:
            # +/-25% deterministic year-to-year variation around the base,
            # plus a small illustrative upward drift over the decade.
            noise = 0.75 + seeded_unit_value(name, year, "passport") * 0.5
            drift = 1 + 0.015 * (year - years[0])
            applications = max(1, round(base * noise * drift))
            rows.append(
                {
                    "country": name,
                    "year": year,
                    "synthetic_passport_applications": applications,
                }
            )
        print(f"  {name:10s}: base ~{base}/year (from RNI {rni}), {years[0]}-{years[-1]}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["country", "year", "synthetic_passport_applications"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} rows ({len(COUNTRIES)} countries x {YEARS_BACK} years) to {out_path}")


if __name__ == "__main__":
    main()
