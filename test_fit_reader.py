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
    Each lap dict: elapsed_time (s), avg_speed (m/s), distance (m).
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
        lap.total_distance     = float(lap_data["distance"])
        builder.add(lap)

    fit_file = builder.build()
    tmp = tempfile.NamedTemporaryFile(suffix=".fit", delete=False)
    tmp.close()
    fit_file.to_file(tmp.name)
    return tmp.name


TEST_LAPS = [
    {"elapsed_time": 600.0,  "avg_speed": 4.167, "distance": 2500.0},
    {"elapsed_time": 1200.0, "avg_speed": 5.556, "distance": 6667.0},
    {"elapsed_time": 300.0,  "avg_speed": 3.0,   "distance": 900.0},
]


class TestFitReader(unittest.TestCase):

    def setUp(self):
        self.fit_path = build_fit_file(TEST_LAPS)

    def tearDown(self):
        if os.path.exists(self.fit_path):
            os.unlink(self.fit_path)

    def test_reads_correct_number_of_sections(self):
        rows = read_fit_file(self.fit_path)
        self.assertEqual(len(rows), 3)

    def test_section_index_is_sequential(self):
        rows = read_fit_file(self.fit_path)
        self.assertEqual([r["section"] for r in rows], [1, 2, 3])

    def test_time_values_are_populated(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNotNone(row["time_s"], f"time_s is None in section {row['section']}")
            self.assertGreater(row["time_s"], 0)

    def test_time_values_match_input(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertAlmostEqual(row["time_s"], lap["elapsed_time"], places=1)

    def test_speed_values_are_populated(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNotNone(row["avg_speed_m_s"])
            self.assertIsNotNone(row["avg_speed_km_h"])
            self.assertGreater(row["avg_speed_m_s"], 0)

    def test_speed_conversion(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertAlmostEqual(
                row["avg_speed_km_h"],
                row["avg_speed_m_s"] * 3.6,
                places=2,
            )

    def test_distance_values_are_populated(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertIsNotNone(row["distance_m"])
            self.assertIsNotNone(row["distance_km"])
            self.assertGreater(row["distance_m"], 0)

    def test_distance_conversion(self):
        rows = read_fit_file(self.fit_path)
        for row in rows:
            self.assertAlmostEqual(
                row["distance_km"],
                row["distance_m"] / 1000,
                places=3,
            )

    def test_distance_values_match_input(self):
        rows = read_fit_file(self.fit_path)
        for row, lap in zip(rows, TEST_LAPS):
            self.assertAlmostEqual(row["distance_m"], lap["distance"], places=0)

    def test_csv_output_has_correct_columns(self):
        rows = read_fit_file(self.fit_path)
        csv_path = tempfile.mktemp(suffix=".csv")
        try:
            write_csv(rows, csv_path)
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
            expected = [
                "source_file", "section", "start_time", "end_time",
                "time_s", "avg_speed_m_s", "avg_speed_km_h",
                "distance_m", "distance_km",
            ]
            self.assertEqual(fieldnames, expected)
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

    def test_csv_row_count(self):
        rows = read_fit_file(self.fit_path)
        csv_path = tempfile.mktemp(suffix=".csv")
        try:
            write_csv(rows, csv_path)
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                csv_rows = list(reader)
            self.assertEqual(len(csv_rows), 3)
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

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
            rows1 = read_fit_file(self.fit_path)
            rows2 = read_fit_file(fit_path2)
            all_rows = rows1 + rows2
            self.assertEqual(len(all_rows), 4)
        finally:
            os.unlink(fit_path2)

    def test_source_file_column_matches_filename(self):
        rows = read_fit_file(self.fit_path)
        expected_name = os.path.basename(self.fit_path)
        for row in rows:
            self.assertEqual(row["source_file"], expected_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
