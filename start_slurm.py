#!/usr/bin/env python3
import config
import os
import re

from datetime import timedelta
from pathlib import Path

num_instances = sum(1 for line in open(config.instances)) - 1
num_runs = len(config.runs)

dir = Path(os.path.dirname(os.path.realpath(__file__)))
script = dir / "run_instance.sh"
post_processing_script = dir / "merge_csv.sh"
assert(script.exists())
assert(post_processing_script.exists())

timeout = config.timeout + timedelta(minutes=1)
sbatch_proc = os.popen(f"sbatch --output=/dev/null --array=1-{num_instances*num_runs} --time={timeout} {str(script.resolve())}")

out = sbatch_proc.read()
print("O", out)

if sbatch_proc.close() is None:
    jobnr = re.findall('\d+$', out)[0]
    print("j", jobnr)
    os.popen(f"sbatch --output=/dev/null --time=1 --dependency=afterok:{jobnr} {str(post_processing_script.resolve())}")


# Submitted batch job 49653
#out = sbatch_proc.read()

# sbatch_proc = os.popen("sbatch", "sbatch", "--output=/dev/null", f"--array=1-{num_instances*num_runs}", f"--time={timeout}", str(script.resolve())).read()


#if sbatch_proc.close() is None:
    #os.execlp("sbatch", "sbatch", "--output=/dev/null", f"--time=1", f"--afterok:{}", str(script.resolve()))
#else:
    #print("Error", out)
#


