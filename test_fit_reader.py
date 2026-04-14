#!/usr/bin/env python3
"""Tests for fit_to_long_format.py using synthetic FIT files built with fit-tool."""

import os
import csv
import unittest
import tempfile

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.profile_type import FileType

from fit_to_long_format import read_fit_file, write_csv


def build_fit_file(laps: list[dict]) -> str:
    """
    Build a valid .fit file using fit-tool and return the temp file path.
    Supported lap dict keys: elapsed_time, avg_speed, distance, avg_heart_rate,
    max_heart_rate, avg_cadence, avg_power, total_calories, total_ascent.
    Caller is responsible for deleting the file.
    """
    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    builder.add(file_id)

    for lap_data in laps:
        lap = LapMessage()
        lap.total_elapsed_time = float(lap_data["elapsed_time"])
        lap.total_timer_time   = float(lap_data.get("timer_time", lap_data["elapsed_time"]))
        lap.avg_speed          = float(lap_data["avg_speed"])
        if lap_data.get("distance") is not None:
            lap.total_distance = float(lap_data["distance"])
        if lap_data.get("avg_heart_rate") is not None:
            lap.avg_heart_rate = int(lap_data["avg_heart_rate"])
        if lap_data.get("max_heart_rate") is not None:
            lap.max_heart_rate = int(lap_data["max_heart_rate"])
        if lap_data.get("avg_cadence") is not None:
            lap.avg_cadence = int(lap_data["avg_cadence"])
        if lap_data.get("avg_power") is not None:
            lap.avg_power = int(lap_data["avg_power"])
        if lap_data.get("total_calories") is not None:
            lap.total_calories = int(lap_data["total_calories"])
        if lap_data.get("total_ascent") is not None:
            lap.total_ascent = int(lap_data["total_ascent"])
        builder.add(lap)

    fit_file = builder.build()
    tmp = tempfile.NamedTemporaryFile(suffix=".fit", delete=False)
    tmp.close()
    fit_file.to_file(tmp.name)
    return tmp.name


TEST_LAPS = [
    {"elapsed_time": 600.0,  "avg_speed": 4.167, "distance": 2500.0,
     "avg_heart_rate": 140, "max_heart_rate": 160, "avg_cadence": 78,
     "avg_power": 220, "total_calories": 200, "total_ascent": 50},
    {"elapsed_time": 1200.0, "avg_speed": 5.556, "distance": 6667.0,
     "avg_heart_rate": 155, "max_heart_rate": 172, "avg_cadence": 82,
     "avg_power": 260, "total_calories": 430, "total_ascent": 30},
    {"elapsed_time": 300.0,  "avg_speed": 3.0,   "distance": 900.0,
     "avg_heart_rate": 120, "max_heart_rate": 135, "avg_cadence": 70,
     "avg_power": 160, "total_calories": 90,  "total_ascent": 10},
]


class TestFitReader(unittest.TestCase):

    def setUp(self):
        self.fit_path = build_fit_file(TEST_LAPS)

    def tearDown(self):
        if os.path.exists(self.fit_path):
            os.unlink(self.fit_path)

    # ── Basic structure ────────────────────────────────────────────────────────

    def test_reads_correct_number_of_sections(self):
        rows = read_fit_file(self.fit_path)
        self.assertEqual(len(rows), 3)

    def test_section_index_is_sequential(self):
        rows = read_fit_file(self.fit_path)
        self.assertEqual([r["section"] for r in rows], [1, 2, 3])

    def test_source_file_column_matches_filename(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertEqual(row["source_file"], os.path.basename(self.fit_path))

    # ── Time ──────────────────────────────────────────────────────────────────

    def test_time_values_are_populated(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNotNone(row["time_s"])
            self.assertGreater(row["time_s"], 0)

    def test_time_values_match_input(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertAlmostEqual(row["time_s"], lap["elapsed_time"], places=1)

    # ── Speed ─────────────────────────────────────────────────────────────────

    def test_speed_values_are_populated(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNotNone(row["avg_speed_m_s"])
            self.assertGreater(row["avg_speed_m_s"], 0)

    def test_speed_km_h_conversion(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertAlmostEqual(row["avg_speed_km_h"], row["avg_speed_m_s"] * 3.6, places=2)

    # ── Distance ──────────────────────────────────────────────────────────────

    def test_distance_values_are_populated(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNotNone(row["distance_m"])
            self.assertGreater(row["distance_m"], 0)

    def test_distance_km_conversion(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertAlmostEqual(row["distance_km"], row["distance_m"] / 1000, places=3)

    def test_distance_values_match_input(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertAlmostEqual(row["distance_m"], lap["distance"], places=0)

    def test_distance_not_derived_when_present(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertFalse(row["distance_derived"])

    def test_distance_derived_when_absent(self):
        """When total_distance is missing, distance should be calculated from speed × time."""
        fit_path = build_fit_file([
            {"elapsed_time": 600.0, "avg_speed": 4.0, "distance": None},
        ])
        try:
            rows = read_fit_file(fit_path)
            self.assertTrue(rows[0]["distance_derived"])
            self.assertAlmostEqual(rows[0]["distance_m"], 4.0 * 600.0, places=0)
        finally:
            os.unlink(fit_path)

    # ── Heart rate ────────────────────────────────────────────────────────────

    def test_avg_hr_populated(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertEqual(row["avg_hr_bpm"], lap["avg_heart_rate"])

    # ── Cadence ───────────────────────────────────────────────────────────────

    def test_avg_cadence_populated(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertEqual(row["avg_cadence_rpm"], lap["avg_cadence"])

    # ── Power ─────────────────────────────────────────────────────────────────

    def test_avg_power_populated(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertEqual(row["avg_power_w"], lap["avg_power"])

    # ── Step / stride length ─────────────────────────────────────────────────

    def test_stride_length_from_file(self):
        """When avg_step_length is in the file (mm), step=mm/1000, stride=step*2."""
        from fit_tool.fit_file_builder import FitFileBuilder
        from fit_tool.profile.messages.file_id_message import FileIdMessage
        from fit_tool.profile.messages.lap_message import LapMessage
        from fit_tool.profile.profile_type import FileType
        builder = FitFileBuilder(auto_define=True, min_string_size=50)
        fid = FileIdMessage(); fid.type = FileType.ACTIVITY
        builder.add(fid)
        lap = LapMessage()
        lap.total_elapsed_time = 600.0
        lap.avg_speed = 4.0
        lap.avg_cadence = 92
        lap.avg_step_length = 1200  # mm → 1.2 m/step → 2.4 m/stride
        builder.add(lap)
        fit_file = builder.build()
        tmp = tempfile.NamedTemporaryFile(suffix=".fit", delete=False)
        tmp.close(); fit_file.to_file(tmp.name)
        try:
            rows = read_fit_file(tmp.name)
            self.assertAlmostEqual(rows[0]["avg_step_length_m"],   1.2, places=3)
            self.assertAlmostEqual(rows[0]["avg_stride_length_m"], 2.4, places=3)
            self.assertFalse(rows[0]["step_length_derived"])
        finally:
            os.unlink(tmp.name)

    def test_stride_length_derived_from_speed_cadence(self):
        """Cadence = strides/min: stride = speed/(cadence/60), step = stride/2."""
        fit_path = build_fit_file([
            {"elapsed_time": 600.0, "avg_speed": 4.0, "distance": 2400.0,
             "avg_cadence": 92},
        ])
        try:
            rows = read_fit_file(fit_path)
            expected_stride = 4.0 / (92 / 60)      # ≈ 2.609 m
            expected_step   = expected_stride / 2   # ≈ 1.304 m
            self.assertAlmostEqual(rows[0]["avg_stride_length_m"], expected_stride, places=3)
            self.assertAlmostEqual(rows[0]["avg_step_length_m"],   expected_step,   places=3)
            self.assertTrue(rows[0]["step_length_derived"])
        finally:
            os.unlink(fit_path)

    def test_stride_length_none_without_cadence(self):
        """Without cadence or step_length in file, both length fields are None."""
        fit_path = build_fit_file([
            {"elapsed_time": 600.0, "avg_speed": 4.0, "distance": 2400.0},
        ])
        try:
            rows = read_fit_file(fit_path)
            self.assertIsNone(rows[0]["avg_step_length_m"])
            self.assertIsNone(rows[0]["avg_stride_length_m"])
        finally:
            os.unlink(fit_path)

    # ── Calories & Ascent ─────────────────────────────────────────────────────

    def test_calories_populated(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertEqual(row["calories_kcal"], lap["total_calories"])

    def test_ascent_populated(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertEqual(row["total_ascent_m"], lap["total_ascent"])

    # ── CSV output ────────────────────────────────────────────────────────────

    def test_csv_contains_expected_columns(self):
        rows = read_fit_file(self.fit_path)
        csv_path = tempfile.mktemp(suffix=".csv")
        try:
            write_csv(rows, csv_path)
            with open(csv_path) as f:
                fieldnames = csv.DictReader(f).fieldnames
            for col in ["source_file", "workout_name", "section", "time_s",
                        "avg_speed_km_h", "distance_km", "avg_hr_bpm",
                        "hr_drift_bpm", "avg_cadence_rpm", "efficiency_factor",
                        "aerobic_decoupling_pct", "avg_power_w",
                        "calories_kcal", "total_ascent_m"]:
                self.assertIn(col, fieldnames)
            # removed fields must be absent
            for col in ["max_hr_bpm", "min_hr_bpm", "max_cadence_rpm",
                        "max_power_w", "max_speed_km_h", "avg_running_cadence_spm"]:
                self.assertNotIn(col, fieldnames)
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

    def test_hr_drift_first_section_is_none(self):
        rows = read_fit_file(self.fit_path)
        self.assertIsNone(rows[0]["hr_drift_bpm"])

    def test_hr_drift_subsequent_sections(self):
        rows = read_fit_file(self.fit_path)
        for i in range(1, len(rows)):
            expected = round(TEST_LAPS[i]["avg_heart_rate"] - TEST_LAPS[i-1]["avg_heart_rate"], 1)
            self.assertAlmostEqual(rows[i]["hr_drift_bpm"], expected, places=1)

    def test_aerobic_decoupling_present_and_consistent(self):
        rows = read_fit_file(self.fit_path)
        # All rows of a session share the same session-level value
        dec_values = {r["aerobic_decoupling_pct"] for r in rows}
        self.assertEqual(len(dec_values), 1)
        self.assertIsNotNone(list(dec_values)[0])

    def test_aerobic_decoupling_weighted_by_duration(self):
        """Longer sections should contribute more to the decoupling calculation."""
        # Two sections: first is short with high EF, second is long with low EF.
        # Duration-weighted result should be dominated by the long second section.
        fit_path = build_fit_file([
            # Short section: high speed/HR → high EF
            {"elapsed_time":  100.0, "avg_speed": 5.0, "distance": 500.0,
             "avg_heart_rate": 120},
            # Long section: same speed, higher HR → lower EF
            {"elapsed_time": 1000.0, "avg_speed": 5.0, "distance": 5000.0,
             "avg_heart_rate": 160},
        ])
        try:
            rows = read_fit_file(fit_path)
            # First half (by time) = section 1 only (100 s < 550 s midpoint)
            # Second half = section 2 (1000 s)
            ef1 = (5.0 * 3.6) / 120   # = 0.150
            ef2 = (5.0 * 3.6) / 160   # = 0.1125
            expected = round((ef1 - ef2) / ef1 * 100, 2)
            self.assertAlmostEqual(rows[0]["aerobic_decoupling_pct"], expected, places=1)
        finally:
            os.unlink(fit_path)

    def test_aerobic_decoupling_none_without_hr(self):
        fit_path = build_fit_file([
            {"elapsed_time": 300.0, "avg_speed": 4.0, "distance": 1200.0},
        ])
        try:
            rows = read_fit_file(fit_path)
            self.assertIsNone(rows[0]["aerobic_decoupling_pct"])
        finally:
            os.unlink(fit_path)

    def test_workout_name_none_for_free_activity(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNone(row["workout_name"])

    def test_workout_name_populated_from_file(self):
        from fit_tool.fit_file_builder import FitFileBuilder
        from fit_tool.profile.messages.file_id_message import FileIdMessage
        from fit_tool.profile.messages.lap_message import LapMessage
        from fit_tool.profile.messages.workout_message import WorkoutMessage
        from fit_tool.profile.profile_type import FileType
        builder = FitFileBuilder(auto_define=True, min_string_size=50)
        fid = FileIdMessage(); fid.type = FileType.ACTIVITY
        builder.add(fid)
        w = WorkoutMessage(); w.workout_name = "Threshold Intervals"
        builder.add(w)
        lap = LapMessage()
        lap.total_elapsed_time = 300.0
        lap.avg_speed = 4.0
        lap.total_distance = 1200.0
        builder.add(lap)
        fit_file = builder.build()
        tmp = tempfile.NamedTemporaryFile(suffix=".fit", delete=False)
        tmp.close(); fit_file.to_file(tmp.name)
        try:
            rows = read_fit_file(tmp.name)
            self.assertEqual(rows[0]["workout_name"], "Threshold Intervals")
        finally:
            os.unlink(tmp.name)

    def test_csv_row_count(self):
        rows = read_fit_file(self.fit_path)
        csv_path = tempfile.mktemp(suffix=".csv")
        try:
            write_csv(rows, csv_path)
            with open(csv_path) as f:
                self.assertEqual(len(list(csv.DictReader(f))), 3)
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_invalid_file_raises(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".fit", delete=False)
        tmp.write(b"not a fit file at all")
        tmp.close()
        try:
            with self.assertRaises(Exception):
                read_fit_file(tmp.name)
        finally:
            os.unlink(tmp.name)

    def test_multiple_files_combined(self):
        fit_path2 = build_fit_file([
            {"elapsed_time": 180.0, "avg_speed": 2.5, "distance": 450.0},
        ])
        try:
            all_rows = read_fit_file(self.fit_path) + read_fit_file(fit_path2)
            self.assertEqual(len(all_rows), 4)
        finally:
            os.unlink(fit_path2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
