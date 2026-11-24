"""Time-in-lead scoring on small hand-made CSV files with a time limit of 10 s."""

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner
from minizinc.result import Status

from mzn_bench.analysis.report_mzn_scores import report_mzn_scores
from mzn_bench.analysis.time_in_lead import TimeInLead, infer_time_limit, run_state
from mzn_bench.cli import main

STATS_KEYS = ["configuration", "problem", "model", "data_file", "status", "time"]
STATS_KEYS += ["method", "objective"]
OBJS_KEYS = ["configuration", "problem", "model", "data_file", "time", "run"]
OBJS_KEYS += ["objective"]

# (problem, method, {configuration: (status, time, final objective, [(time, objective), ...])})
INSTANCES = [
    # A solves at 2.5 s, B at 6 s
    (
        "sat",
        "satisfy",
        {
            "A": ("SATISFIED", 2.5, None, [(2.5, None)]),
            "B": ("SATISFIED", 6.0, None, [(6.0, None)]),
        },
    ),
    # A: 10 from 1 s, 8 from 4 s. B: 9 from 3 s, proves 9 optimal at 7 s.
    (
        "min",
        "minimize",
        {
            "A": ("SATISFIED", 10.3, 8, [(1.2, 10), (4.0, 8)]),
            "B": ("OPTIMAL_SOLUTION", 7.5, 9, [(3.0, 9)]),
        },
    ),
    # A: 5 from 1 s, 7 from 3 s. B: 6 from 2 s, 8 from 8 s.
    (
        "max",
        "maximize",
        {
            "A": ("SATISFIED", 10.2, 7, [(1.0, 5), (3.0, 7)]),
            "B": ("SATISFIED", 10.4, 8, [(2.0, 6), (8.0, 8)]),
        },
    ),
    # Neither finds a solution
    (
        "unsolved",
        "minimize",
        {
            "A": ("UNKNOWN", 10.1, None, []),
            "B": ("ERROR", 0.3, None, []),
        },
    ),
    # Both find 5 at 2 s
    (
        "tie",
        "minimize",
        {
            "A": ("SATISFIED", 10.1, 5, [(2.0, 5)]),
            "B": ("SATISFIED", 10.1, 5, [(2.0, 5)]),
        },
    ),
]

# Score of A against B on each instance
EXPECTED_A = {
    "sat": (0.5 + 4 + 5 * 0.5) / 10,  # t=1 tie, t=2..5 A leads, t=6..10 tie
    "min": 9 / 10,  # B leads only at t=3 (9 against 10)
    "max": 6 / 10,  # B leads at t=2 and t=8..10
    "unsolved": 0.5,
    "tie": 0.5,
}


@pytest.fixture
def csv_files(tmp_path: Path):
    stats, objs = tmp_path / "stats.csv", tmp_path / "objs.csv"
    with stats.open("w") as sf, objs.open("w") as of:
        sw = csv.DictWriter(sf, STATS_KEYS, dialect="unix")
        ow = csv.DictWriter(of, OBJS_KEYS, dialect="unix")
        sw.writeheader()
        ow.writeheader()
        for problem, method, runs in INSTANCES:
            base = {"problem": problem, "model": f"{problem}.mzn", "data_file": ""}
            for conf, (status, time, obj, trace) in runs.items():
                sw.writerow(
                    base
                    | {"configuration": conf, "status": status, "time": time}
                    | {
                        "method": None if status == "ERROR" else method,
                        "objective": obj,
                    }
                )
                for t, o in trace:
                    ow.writerow(
                        base
                        | {"configuration": conf, "time": t, "run": "results"}
                        | {"objective": o}
                    )
    return stats, objs


def table(out: str) -> dict:
    """Parse a tsv table into {row label: {column label: cell}}."""
    lines = [[c.strip() for c in line.split("\t")] for line in out.splitlines()]
    return {row[0]: dict(zip(lines[0][1:], row[1:])) for row in lines[1:]}


def read(stats: Path):
    df = pd.read_csv(stats)
    df["data_file"] = df["data_file"].fillna("")
    return df


def test_infer_time_limit(csv_files):
    stats, _ = csv_files
    assert infer_time_limit(read(stats)) == 10


def test_infer_time_limit_all_finished():
    df = pd.DataFrame(
        {"status": ["SATISFIED", "OPTIMAL_SOLUTION"], "time": [3.2, 7.4]}
        | {"method": ["satisfy", "minimize"]}
    )
    assert infer_time_limit(df) == 8


@pytest.mark.parametrize("problem", list(EXPECTED_A))
def test_per_instance(csv_files, problem):
    stats, objs = csv_files
    df = read(stats)
    lead = TimeInLead(df, pd.read_csv(objs), 10)
    sub = df[df["problem"] == problem]
    a, b = lead.score(sub, "A", "B")
    assert a == pytest.approx(EXPECTED_A[problem])
    assert a + b == pytest.approx(1.0)
    assert lead.score(sub, "B", "A") == pytest.approx((b, a))


def test_report_total(csv_files):
    stats, objs = csv_files
    out = report_mzn_scores("all", stats, "tsv", score="time-in-lead", objectives=objs)
    rows = table(out)
    total = sum(EXPECTED_A.values())
    assert float(rows["A"]["all"]) == pytest.approx(total, abs=0.005)
    assert float(rows["B"]["all"]) == pytest.approx(5 - total, abs=0.005)


def test_report_baseline_per_problem(csv_files):
    stats, objs = csv_files
    out = report_mzn_scores(
        "problem", stats, "tsv", "B", score="time-in-lead", objectives=objs
    )
    cells = table(out)["A"]
    assert set(cells) == set(EXPECTED_A)
    for problem, a in EXPECTED_A.items():
        assert cells[problem] == "%.2f (%.2f)" % (a, 1 - a)


def test_cli_old_name(csv_files):
    stats, objs = csv_files
    runner = CliRunner()
    args = ["--score", "time-in-lead", "--objectives", str(objs), "--output-mode"]
    args += ["tsv", str(stats)]
    old = runner.invoke(main, ["report-mzn-scores"] + args)
    new = runner.invoke(main, ["report-scores"] + args)
    assert old.exit_code == 0, old.output
    assert new.output == old.output
    rows = table(new.output)
    assert float(rows["A"]["all"]) == pytest.approx(3.2)
    assert float(rows["B"]["all"]) == pytest.approx(1.8)


def test_cli_needs_objectives(csv_files):
    stats, _ = csv_files
    result = CliRunner().invoke(
        main, ["report-scores", "--score", "time-in-lead", str(stats)]
    )
    assert result.exit_code != 0
    assert "--objectives" in result.output


def test_missing_run_is_skipped(csv_files):
    stats, objs = csv_files
    df = read(stats)
    df = df[~((df["configuration"] == "B") & (df["problem"] == "sat"))]
    lead = TimeInLead(df, pd.read_csv(objs), 10)
    a, b = lead.score(df, "A", "B")
    assert a + b == pytest.approx(4.0)


def test_unsat_optimization_is_best_state():
    row = run_state("minimize", Status.UNSATISFIABLE, 4.5, None, [], [], 10)
    assert np.all(np.isneginf(row[:4])) and np.all(np.isposinf(row[4:]))


def test_events_after_time_limit_are_ignored():
    row = run_state(
        "maximize",
        Status.SATISFIED,
        12.0,
        3,
        np.array([2.0, 11.0]),
        np.array([1.0, 3.0]),
        10,
    )
    assert list(row[1:]) == [-np.inf] + [1.0] * 9
