# MiniZinc SLURM

This is a small collection of scripts that allow you to run benchmarks on a set
of MiniZinc instance using MiniZinc Python. The process is split into several
steps to be easily customisable to different kinds of possible benchmarks.


## Preparation

1. Create a CSV file for the MiniZinc instances containing *problem*, *model*,
   *data_file*. If you store the instances in the MiniZinc benchmarks
   repository structure, then you can use the `collect_instances.py` script:
```
collect_instances <directory> > instances.csv
```
2. Instantiate a benchmarking environment. This environment should at least
   contain a Python virtual environment with *MiniZinc SLURM* your the
   benchmarking scripts, but you can also set up environmental variables, like
   `PATH`, and load cluster modules. The following script, `bench_env.sh`,
   provides an example environment that can be loaded using `source
   bench_env.sh`:
```bash
if [[ "${BASH_SOURCE[0]}" = "${0}" ]]; then
    >&2 echo "Remember: you need to run me as 'source bench_env.sh', not execute it!"
    exit
fi

# Create or activate Python virtual environment
if [ -d venv ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
    python3 -m pip install git+https://github.com/Dekker1/minizinc-slurm
fi

# Set other environment variables and load cluster modules
module load MiniZinc/2.4.3
```
3. Create a MiniZinc SLURM benchmarking script. This script will contain the
   configuration of where the instance file is located, what MiniZinc/Solver
   configurations to run for every instance, and how SLURM itself should be
   configured. The script mainly consist of a call to `schedule` in
   `minizinc_slurm`. For example a benchmarking script that runs Gecode and
   Chuffed for 20 minutes might look like this:

```python
from datetime import timedelta
from pathlib import Path

import minizinc

from minizinc_slurm import Configuration, schedule

schedule(
    instances=Path("./instances.csv"),
    timeout=timedelta(minutes=20),
    configurations=[
        Configuration(name="Gecode", solver=minizinc.Solver.lookup("gecode")),
        Configuration(name="Chuffed", solver=minizinc.Solver.lookup("chuffed")),
    ],
    nodelist=["critical001"],
)
```

These are all the possible arguments to `schedule`:

- `instances: Path` - The path to the instances file.
- `timeout: timedelta` - The timeout set for the MiniZinc process.
- `configurations: Iterable[Configuration]` - MiniZinc solving configurations
  (see below for details).
- `nodelist: Iterable[str]` - A list of nodes on which SLURM is allowed to
  schedule the tasks.
- `output_dir: Path = Path.cwd() / "results"` - The directory in which the raw
  results will be placed. This directory will be created if it does not yet
  exist.
- `job_name: str = "MiniZinc Benchmark"` - The SLURM job name.
- `cpus_per_task: int = 1` - The number of CPU cores required for each task.
- `memory: int = 4096` - The maximum memory used for each task.

A `Configuration` object has the following attributes:

- `name: str` - Configuration name used in the output.
- `solver: minizinc.Solver` - MiniZinc Python solver configuration.
- `minizinc: Optional[Path] = None` - Path to a specific MiniZinc executable.
  If `None` is provided, then the first `minizinc` executable on the `PATH`
  will be used.
- `processes: Optional[int] = None` - Number of processes to be used by the
  solver.
- `random_seed: Optional[int] = None` - Random seed to be used by the solver.
- `free_search: bool = False` - Solver can determine its own search heuristic.
- `optimisation_level: Optional[int] = None` - MiniZinc compilation optimisation level, e.g., `-O3`.
- `other_flags: Dict[str, Any] = field(default_factory=dict)` - A mapping of
  flag name to value of other flags to be provided to the compiler/solver

## Schedule SLURM jobs

The job now has to be started on the cluster with the right number of tasks
(one for every instance/solver combination). Luckily, the MiniZinc SLURM
benchmarking script that you've created in the previous step should take care
of all of this. So once we ensure that our environment is ready for our
benchmark, we can execute our script and our job will be scheduled.

For example, if we had created a script `bench_env.sh` with our benchmarking
environment and a script `start_bench.py` with our MiniZinc SLURM `schedule`
call, then the following code should schedule our job:
```bash
source bench_env.sh
python start_bench.py
```
You can keep track of the status of your job using the `squeue` command.

**WARNING:** Once the job has started the CSV file containing the instances and
the instance files themselves should not be changed or moved until the full
benchmark is finished. This could causes error or, even worse, inconsistent
results.

**Note:** If you find a mistake after you have scheduled your job, then you
should cancel the job as soon as possible. This can be done by using the
`scancel` command. This command will take the `job_id`, shown when your job is
scheduled, as an argument.

## Collect information

Once the job is finished, it is time to get your data wrangling pants on! This
repository contains some scripts that might be helpful in locating and
formatting the information that you need. Some scripts might be used directly
while other might need some customising to fit your purpose. Note that these
scripts might require some extra dependencies. For this reason, these scripts
are not expected to work unless this package is installed as `pip install
minizinc_slurm[scripts]`. This allows us to install a minimal version on the
running cluster and this more complete version locally while processing the
data.

### General aggregation

The following scripts can help gather the raw `*_stats.yml`/`*_sol.yml` files and combine
them for further use:

- `collect_statistics <result_dir> <statistics.csv>` - This script gathers all
  statistical information given by MiniZinc and the used solvers and combines
  them in a single CSV file.

### Tabulation

The following scripts filter and tabulate specific statistics.

- `report_status <statistics.csv>` - This script will report the number of
  occurrences of the various solving status of your MiniZinc tasks. Please
  consult the `-h` flag to display all options.

### Graph generation

*TODO: Not yet Implemented*
