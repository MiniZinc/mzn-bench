# content of test_sample.py
from datetime import timedelta
from pathlib import Path
import pytest

import minizinc

from mzn_bench import Configuration, schedule, collect_objectives_, collect_statistics_, check_solutions_, check_statuses_

import sys
def test_run():
   output_dir="tests/results"

   schedule(
           instances=Path("./tests/test.csv"),
           timeout=timedelta(seconds=5),
           configurations=[
               Configuration(name="Gecode", solver=minizinc.Solver.lookup("gecode")),
               Configuration(name="Chuffed", solver=minizinc.Solver.lookup("chuffed")),
               ],
           output_dir=Path(output_dir),
           nodelist=None  # local runner
           )
    
   collect_objectives_([output_dir], f"{output_dir}/objs.csv")
   collect_statistics_([output_dir], f"{output_dir}/stats.csv")

   with pytest.raises(SystemExit) as error:
       check_solutions_(0, ".", output_dir, ["-s"])
       assert error.code == pytest.ExitCode.OK

   with pytest.raises(SystemExit) as error:
       check_statuses_(output_dir, ["-s"])
       assert error.code == pytest.ExitCode.OK

