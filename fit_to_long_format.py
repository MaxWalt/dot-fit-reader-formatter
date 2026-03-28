#!/usr/bin/env python3
"""
FIT file reader that extracts lap/section data into a long-format CSV.

Outputs per section: time, speed, distance, HR, cadence, power,
altitude, temperature, calories, ascent/descent, and more.
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


def _r(value, places=2):
    """Round a value if not None."""
    return round(value, places) if value is not None else None


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
        # ── Time ──────────────────────────────────────────────────────────────
        elapsed_time = lap.get("total_elapsed_time")
        timer_time   = lap.get("total_timer_time")
        moving_time  = lap.get("total_moving_time")
        # Prefer moving time → timer time → elapsed time
        section_time = moving_time if moving_time is not None else (
                       timer_time  if timer_time  is not None else elapsed_time)

        # ── Speed ─────────────────────────────────────────────────────────────
        # Prefer enhanced fields (sub-meter precision) when available
        avg_speed = lap.get("enhanced_avg_speed") or lap.get("avg_speed")
        max_speed = lap.get("enhanced_max_speed") or lap.get("max_speed")

        # ── Distance ──────────────────────────────────────────────────────────
        distance = lap.get("total_distance")
        # If absent or zero, derive from avg_speed × time
        if (distance is None or distance == 0) and avg_speed and section_time:
            distance = avg_speed * section_time
            distance_derived = True
        else:
            distance_derived = False

        # ── Heart rate ────────────────────────────────────────────────────────
        avg_hr  = lap.get("avg_heart_rate")
        max_hr  = lap.get("max_heart_rate")
        min_hr  = lap.get("min_heart_rate")

        # ── Cadence ───────────────────────────────────────────────────────────
        # avg_cadence is steps/min (running) or rpm (cycling)
        avg_cadence = lap.get("avg_cadence")
        max_cadence = lap.get("max_cadence")
        # Running-specific: avg_running_cadence is strides/min (×2 = steps/min)
        avg_run_cadence = lap.get("avg_running_cadence")

        # ── Power (cycling / running) ─────────────────────────────────────────
        avg_power        = lap.get("avg_power")
        max_power        = lap.get("max_power")
        normalized_power = lap.get("normalized_power")

        # ── Altitude ──────────────────────────────────────────────────────────
        avg_alt = lap.get("enhanced_avg_altitude") or lap.get("avg_altitude")
        max_alt = lap.get("enhanced_max_altitude") or lap.get("max_altitude")
        min_alt = lap.get("enhanced_min_altitude") or lap.get("min_altitude")
        ascent  = lap.get("total_ascent")
        descent = lap.get("total_descent")

        # ── Other ─────────────────────────────────────────────────────────────
        calories    = lap.get("total_calories")
        temperature = lap.get("avg_temperature")
        avg_grade   = lap.get("avg_grade")
        sport       = lap.get("sport")
        sub_sport   = lap.get("sub_sport")
        start_time  = lap.get("start_time")
        timestamp   = lap.get("timestamp")

        row = {
            # Metadata
            "source_file":        os.path.basename(fit_path),
            "section":            i,
            "sport":              sport,
            "sub_sport":          sub_sport,
            "start_time":         str(start_time) if start_time else None,
            "end_time":           str(timestamp)  if timestamp  else None,
            # Time
            "time_s":             _r(section_time, 2),
            "elapsed_time_s":     _r(elapsed_time, 2),
            # Speed
            "avg_speed_m_s":      _r(avg_speed, 4),
            "avg_speed_km_h":     _r(avg_speed * 3.6, 4) if avg_speed is not None else None,
            "max_speed_m_s":      _r(max_speed, 4),
            "max_speed_km_h":     _r(max_speed * 3.6, 4) if max_speed is not None else None,
            # Distance
            "distance_m":         _r(distance, 2),
            "distance_km":        _r(distance / 1000, 4) if distance is not None else None,
            "distance_derived":   distance_derived,
            # Heart rate
            "avg_hr_bpm":         avg_hr,
            "max_hr_bpm":         max_hr,
            "min_hr_bpm":         min_hr,
            # Cadence
            "avg_cadence_rpm":    avg_cadence,
            "max_cadence_rpm":    max_cadence,
            "avg_running_cadence_spm": avg_run_cadence,
            # Power
            "avg_power_w":        avg_power,
            "max_power_w":        max_power,
            "normalized_power_w": normalized_power,
            # Altitude
            "avg_altitude_m":     _r(avg_alt, 1),
            "max_altitude_m":     _r(max_alt, 1),
            "min_altitude_m":     _r(min_alt, 1),
            "total_ascent_m":     ascent,
            "total_descent_m":    descent,
            "avg_grade_pct":      _r(avg_grade, 2),
            # Other
            "calories_kcal":      calories,
            "avg_temperature_c":  temperature,
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
        description="Convert .fit file(s) to a long-format CSV with section metrics."
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
            with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 160):
                print(df.to_string(index=False))
        else:
            cols = ["source_file", "section", "time_s", "avg_speed_km_h", "distance_km",
                    "avg_hr_bpm", "avg_cadence_rpm"]
            header = "  ".join(f"{c:<22}" for c in cols)
            print(header)
            print("-" * len(header))
            for row in all_rows:
                line = "  ".join(f"{str(row.get(c, '')):<22}" for c in cols)
                print(line)


if __name__ == "__main__":
    main()
