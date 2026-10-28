#!/usr/bin/env python3
"""Ghost Load detector: finds 'ghosts' in hourly electricity data.

No AI here on purpose: the numbers come from plain, checkable code.
The AI (story.py) only turns these verified findings into stories.

Input CSV columns: timestamp (ISO format), kwh (energy in that hour)
"""
import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from datetime import datetime


def load(path):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append((datetime.fromisoformat(row["timestamp"]), float(row["kwh"])))
    rows.sort()
    return rows


def recurring_hour_ghosts(rows, rate):
    """An hour of the day that is regularly far above its neighbouring hours."""
    by_hour = defaultdict(list)
    for ts, k in rows:
        by_hour[ts.hour].append((ts.date(), k))
    med = {h: st.median(k for _, k in v) for h, v in by_hour.items()}
    findings = []
    for h in range(24):
        nb = (med[(h - 1) % 24] + med[(h + 1) % 24]) / 2
        excess = med[h] - nb
        if excess >= 0.4 and med[h] >= 1.8 * nb:
            hits = [k - nb for _, k in by_hour[h] if k - nb >= 0.5 * excess]
            extra = sum(hits)
            findings.append({
                "kind": "recurring_hour",
                "title": f"The {h:02d}:00 visitor",
                "facts": {
                    "hour": f"{h:02d}:00",
                    "typical_usage_kwh": round(med[h], 2),
                    "usual_usage_in_neighbouring_hours_kwh": round(nb, 2),
                    "nights_it_appeared": len(hits),
                    "out_of_days": len(by_hour[h]),
                    "extra_energy_kwh": round(extra, 1),
                    "extra_cost": round(extra * rate, 2),
                },
            })
    return findings


def baseload_step(rows, rate):
    """A sudden, lasting rise in the lowest daily usage (something left on)."""
    daily_min = {}
    for ts, k in rows:
        d = ts.date()
        daily_min[d] = min(daily_min.get(d, 1e9), k)
    days = sorted(daily_min)
    vals = [daily_min[d] for d in days]
    if len(vals) < 12:
        return []

    def sse(seg):
        m = sum(seg) / len(seg)
        return sum((x - m) ** 2 for x in seg)

    best_i = min(range(4, len(vals) - 4), key=lambda i: sse(vals[:i]) + sse(vals[i:]))
    before, after = st.median(vals[:best_i]), st.median(vals[best_i:])
    shift = after - before
    if shift >= 0.08 and shift >= 0.25 * before:
        days_after = len(vals) - best_i
        extra = shift * 24 * days_after
        return [{
            "kind": "baseload_step",
            "title": "The thing that never sleeps",
            "facts": {
                "first_day_noticed": str(days[best_i]),
                "lowest_hourly_usage_before_kwh": round(before, 2),
                "lowest_hourly_usage_after_kwh": round(after, 2),
                "constant_extra_draw_watts": round(shift * 1000),
                "days_since": days_after,
                "extra_energy_kwh": round(extra, 1),
                "extra_cost": round(extra * rate, 2),
                "projected_extra_cost_per_30_days": round(shift * 24 * 30 * rate, 2),
            },
        }]
    return []


def one_off_surges(rows, rate):
    """A single hour far above what that hour normally looks like."""
    by_hour = defaultdict(list)
    for ts, k in rows:
        by_hour[ts.hour].append(k)
    stats = {}
    for h, v in by_hour.items():
        m = st.median(v)
        mad = st.median(abs(x - m) for x in v)
        stats[h] = (m, max(1.4826 * mad, 0.05))
    findings = []
    for ts, k in rows:
        m, scale = stats[ts.hour]
        if (k - m) / scale >= 6 and k - m >= 1.5:
            findings.append({
                "kind": "one_off_surge",
                "title": "The poltergeist surge",
                "facts": {
                    "when": ts.strftime("%Y-%m-%d %H:%M"),
                    "usage_kwh": round(k, 2),
                    "normal_for_that_hour_kwh": round(m, 2),
                    "extra_energy_kwh": round(k - m, 1),
                    "extra_cost": round((k - m) * rate, 2),
                },
            })
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--rate", type=float, default=0.30,
                    help="price per kWh (default 0.30 is an ASSUMPTION; use your own tariff)")
    ap.add_argument("--out", default="findings.json")
    args = ap.parse_args()

    rows = load(args.csv_path)
    findings = (baseload_step(rows, args.rate)
                + recurring_hour_ghosts(rows, args.rate)
                + one_off_surges(rows, args.rate))
    for i, f in enumerate(findings, 1):
        f["id"] = i

    with open(args.out, "w") as f:
        json.dump({"rate_per_kwh": args.rate, "readings": len(rows), "findings": findings}, f, indent=2)

    print(f"Read {len(rows)} readings. Found {len(findings)} ghost(s):")
    for f in findings:
        print(f"  {f['id']}. {f['title']}  ->  {f['facts']}")
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
