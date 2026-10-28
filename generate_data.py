#!/usr/bin/env python3
"""Generate a month of hourly household electricity readings with hidden 'ghosts'.

Use this to test Ghost Load before you plug in your real meter / solar data.
Output CSV columns: timestamp, kwh   (energy used in that hour)
"""
import argparse
import csv
import random
from datetime import datetime, timedelta


def normal_usage(hour, weekend):
    """kWh a normal, A/C-heavy household uses in one hour."""
    if 0 <= hour < 6:
        return 0.30
    if 6 <= hour < 9:
        return 0.80
    if 9 <= hour < 17:
        return 0.85 if weekend else 0.55
    if 17 <= hour < 23:
        return 1.40
    return 0.60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sample_usage.csv")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    random.seed(args.seed)
    start = datetime(2026, 9, 27)
    step_day = 12                 # a new always-on device appears on this day
    surge_day, surge_hour = 19, 11  # one-off power surge

    rows = []
    for d in range(args.days):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            weekend = ts.weekday() in (5, 6)
            kwh = normal_usage(h, weekend) * random.uniform(0.9, 1.1)
            if d >= step_day:                      # ghost 1: phantom load
                kwh += 0.15
            if h == 3 and random.random() < 0.9:   # ghost 2: the 3 AM knock
                kwh += 0.9 * random.uniform(0.9, 1.1)
            if (d, h) == (surge_day, surge_hour):  # ghost 3: poltergeist surge
                kwh += 4.0
            rows.append((ts.isoformat(timespec="minutes"), round(kwh, 3)))

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "kwh"])
        w.writerows(rows)

    print(f"Wrote {len(rows)} hourly readings to {args.out}")
    print("Planted ghosts (for checking the detector):")
    print(f"  1. Always-on load of ~150 W starting {(start + timedelta(days=step_day)).date()}")
    print("  2. A ~0.9 kWh spike at 03:00 on about 90% of nights")
    print(f"  3. A one-off surge on {(start + timedelta(days=surge_day)).date()} at {surge_hour:02d}:00")


if __name__ == "__main__":
    main()
