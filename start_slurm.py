#!/usr/bin/env python3
import config
import os

from datetime import timedelta
from pathlib import Path

num_instances = sum(1 for line in open(config.instances)) - 1
num_solvers = len(config.solvers)

dir = Path(os.path.dirname(os.path.realpath(__file__)))
script = dir / "run_instance.sh"
assert(script.exists())

timeout = config.timeout + timedelta(minutes=1)

os.execlp("sbatch", "sbatch", "--output=/dev/null", f"--array=1-{num_instances*num_solvers}", f"--time={timeout}", str(script.resolve()))
