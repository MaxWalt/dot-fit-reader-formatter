#!/usr/bin/env python3
"""
FIT file reader that extracts lap/section data into a long-format CSV.

Outputs: section index, time (seconds), avg_speed (m/s & km/h), distance (m & km)
"""

import argparse
import sys
import csv
import os
from pathlib import Path

try:
    from garmin_fit_sdk import Decoder, Stream
except ImportError:
    print("Error: garmin-fit-sdk not installed. Run: pip install garmin-fit-sdk", file=sys.stderr)
    sys.exit(1)

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def read_fit_file(fit_path: str) -> list[dict]:
    """Read a .fit file and return lap/section records in long format."""
    stream = Stream.from_file(fit_path)
    decoder = Decoder(stream)

    if not decoder.is_fit():
        raise ValueError(f"Not a valid FIT file: {fit_path}")

    messages, errors = decoder.read(
        apply_scale_and_offset=True,
        convert_datetimes_to_dates=True,
        convert_types_to_strings=True,
    )

    if errors:
        print(f"Warning: {len(errors)} decode error(s) in {fit_path}", file=sys.stderr)

    laps = messages.get("lap_mesgs", [])
    if not laps:
        raise ValueError(f"No lap/section messages found in {fit_path}")

    rows = []
    for i, lap in enumerate(laps, start=1):
        elapsed_time = lap.get("total_elapsed_time")   # seconds
        timer_time   = lap.get("total_timer_time")     # active time, seconds
        avg_speed    = lap.get("avg_speed")            # m/s
        distance     = lap.get("total_distance")       # meters
        start_time   = lap.get("start_time")
        timestamp    = lap.get("timestamp")

        # Prefer timer_time (moving time) but fall back to elapsed_time
        section_time = timer_time if timer_time is not None else elapsed_time

        row = {
            "source_file":       os.path.basename(fit_path),
            "section":           i,
            "start_time":        str(start_time) if start_time else None,
            "end_time":          str(timestamp)  if timestamp  else None,
            "time_s":            round(section_time, 2) if section_time is not None else None,
            "avg_speed_m_s":     round(avg_speed, 4)    if avg_speed   is not None else None,
            "avg_speed_km_h":    round(avg_speed * 3.6, 4) if avg_speed is not None else None,
            "distance_m":        round(distance, 2)     if distance    is not None else None,
            "distance_km":       round(distance / 1000, 4) if distance is not None else None,
        }
        rows.append(row)

    return rows


def write_csv(rows: list[dict], output_path: str) -> None:
    if not rows:
        print("No data to write.", file=sys.stderr)
        return
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} section(s) to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert .fit file(s) to a long-format CSV with section time, avg speed and distance."
    )
    parser.add_argument(
        "fit_files",
        nargs="+",
        metavar="FILE.fit",
        help="One or more .fit files to process",
    )
    parser.add_argument(
        "-o", "--output",
        default="sections_long_format.csv",
        metavar="OUTPUT.csv",
        help="Output CSV file path (default: sections_long_format.csv)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_table",
        help="Print a summary table to stdout",
    )
    args = parser.parse_args()

    all_rows = []
    for fit_path in args.fit_files:
        if not Path(fit_path).exists():
            print(f"Error: file not found: {fit_path}", file=sys.stderr)
            continue
        try:
            rows = read_fit_file(fit_path)
            all_rows.extend(rows)
            print(f"Read {len(rows)} section(s) from {fit_path}")
        except Exception as e:
            print(f"Error processing {fit_path}: {e}", file=sys.stderr)

    if not all_rows:
        print("No data extracted.", file=sys.stderr)
        sys.exit(1)

    write_csv(all_rows, args.output)

    if args.print_table:
        if HAS_PANDAS:
            df = pd.DataFrame(all_rows)
            with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 120):
                print(df.to_string(index=False))
        else:
            # Fallback plain text table
            cols = ["source_file", "section", "time_s", "avg_speed_km_h", "distance_km"]
            header = "  ".join(f"{c:<20}" for c in cols)
            print(header)
            print("-" * len(header))
            for row in all_rows:
                line = "  ".join(f"{str(row.get(c, '')):<20}" for c in cols)
                print(line)


if __name__ == "__main__":
    main()
