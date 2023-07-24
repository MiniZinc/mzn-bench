# content of test_sample.py
from datetime import timedelta
from pathlib import Path
import pytest
from bokeh.plotting import show
from mzn_bench.analysis.plot import plot_all_instances
from mzn_bench.analysis.collect import read_csv

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
    output_dir = "tests/results"

    # paths
    INSTANCES = "./tests/test.csv"
    OBJS = f"{output_dir}/objs.csv"
    STATS = f"{output_dir}/stats.csv"

    schedule(
        instances=Path(INSTANCES),
        timeout=timedelta(seconds=5),
        configurations=[
            Configuration(name="Gecode", solver=minizinc.Solver.lookup("gecode")),
            Configuration(name="Chuffed", solver=minizinc.Solver.lookup("chuffed")),
        ],
        output_dir=Path(output_dir),
        nodelist=None,  # local runner
    )

    collect_objectives_([output_dir], OBJS)
    collect_statistics_([output_dir], STATS)

    with pytest.raises(SystemExit) as error:
        check_solutions_(0, "./tests", output_dir, ["-s"])
        assert error.code == pytest.ExitCode.OK

    with pytest.raises(SystemExit) as error:
        check_statuses_(output_dir, ["-s"])
        assert error.code == pytest.ExitCode.OK

    objs, stats = read_csv(OBJS, STATS)
    show(plot_all_instances(objs, stats))
