# content of test_sample.py
from datetime import timedelta
from pathlib import Path
import pytest
from mzn_bench.analysis.collect import read_csv

try:
    from bokeh.plotting import output_file, save
    from mzn_bench.analysis.plot import plot_all_instances
except ImportError:
    output_file=None

import minizinc

from mzn_bench import (
    Configuration,
    schedule,
    collect_objectives_,
    collect_statistics_,
    check_solutions_,
    check_statuses_,
)


def test_run():
    OUTPUT_DIR = "tests/results"

    # paths
    INSTANCES = "./tests/test.csv"
    OBJS = f"{OUTPUT_DIR}/objs.csv"
    STATS = f"{OUTPUT_DIR}/stats.csv"
    PLOT = f"{OUTPUT_DIR}/plot.html"

    schedule(
        instances=Path(INSTANCES),
        timeout=timedelta(seconds=5),
        configurations=[
            Configuration(name="Gecode", solver=minizinc.Solver.lookup("gecode")),
            Configuration(name="Chuffed", solver=minizinc.Solver.lookup("chuffed")),
        ],
        output_dir=Path(OUTPUT_DIR),
        nodelist=None,  # local runner
    )

    collect_objectives_([OUTPUT_DIR], OBJS)
    collect_statistics_([OUTPUT_DIR], STATS)

    with pytest.raises(SystemExit) as error:
        check_solutions_(0, "./tests", OUTPUT_DIR, ["-s"])
        assert error.code == pytest.ExitCode.OK

    with pytest.raises(SystemExit) as error:
        check_statuses_(OUTPUT_DIR, ["-s"])
        assert error.code == pytest.ExitCode.OK

    # Use `poetry install --all-extras` to test this part
    if output_file is not None:
        objs, stats = read_csv(OBJS, STATS)
        output_file(filename=PLOT, title="Plot")
        p=plot_all_instances(objs, stats)
        save(p)
