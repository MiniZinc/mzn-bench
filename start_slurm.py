#!/usr/bin/env python3
import config
import os

from pathlib import Path

num_instances = sum(1 for line in open(config.instances)) - 1
num_solvers = len(config.solvers)

dir = Path(os.path.dirname(os.path.realpath(__file__)))
script = dir / "run_instance.sh"
assert(script.exists())

os.execlp("sbatch", "sbatch", "--output=/dev/null", f"--array=1-{num_instances*num_solvers}", str(script.resolve()))
