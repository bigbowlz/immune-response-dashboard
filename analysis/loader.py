"""Load cell-count.csv into the normalized tables. Standard library only."""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from analysis.schema import POPULATIONS

SUBJECT_COLUMNS = ("project", "condition", "age", "sex", "treatment", "response")
SAMPLE_COLUMNS = ("sample_type", "time_from_treatment_start")
REQUIRED_COLUMNS = ("subject", "sample") + SUBJECT_COLUMNS + SAMPLE_COLUMNS + POPULATIONS


@dataclass(frozen=True)
class LoadReport:
    rows: int
    samples: int
    subjects: int


def _int(value: str, *, row: int, column: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"row {row}: column {column!r} is not an integer: {value!r}") from None


def load_csv(csv_path: Path, conn: sqlite3.Connection) -> LoadReport:
    with open(csv_path, newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing columns: {sorted(missing)}")

        subjects: dict[str, tuple] = {}
        samples: list[tuple] = []
        counts: list[tuple] = []
        seen_samples: set[str] = set()

        for i, row in enumerate(reader, start=2):  # line numbers, header is line 1
            subject_row = (
                row["subject"], row["project"], row["condition"],
                _int(row["age"], row=i, column="age"), row["sex"], row["treatment"],
                row["response"] or None,
            )
            previous = subjects.setdefault(row["subject"], subject_row)
            if previous != subject_row:
                raise ValueError(f"row {i}: subject {row['subject']!r} has inconsistent metadata")

            if row["sample"] in seen_samples:
                raise ValueError(f"row {i}: duplicate sample id {row['sample']!r}")
            seen_samples.add(row["sample"])
            samples.append((
                row["sample"], row["subject"], row["sample_type"],
                _int(row["time_from_treatment_start"], row=i, column="time_from_treatment_start"),
            ))
            for population in POPULATIONS:
                counts.append((row["sample"], population, _int(row[population], row=i, column=population)))

    with conn:
        conn.executemany("INSERT INTO subjects VALUES (?, ?, ?, ?, ?, ?, ?)", subjects.values())
        conn.executemany("INSERT INTO samples VALUES (?, ?, ?, ?)", samples)
        conn.executemany("INSERT INTO cell_counts VALUES (?, ?, ?)", counts)

    return LoadReport(rows=len(samples), samples=len(seen_samples), subjects=len(subjects))
