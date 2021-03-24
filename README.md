# MiniZinc Bench

This is a small collection of scripts that allow you to run benchmarks on a set
of MiniZinc instance using MiniZinc Python. The process is split into several
steps to be easily customisable to different kinds of possible benchmarks.

> Currently, the only supported way of running benchmarks is through
> [SLURM](https://slurm.schedmd.com/). Other methods may become available in the
> future.

## Preparation

1. Create a CSV file for the MiniZinc instances containing _problem_, _model_,
   _data_file_. If you store the instances in the MiniZinc benchmarks
   repository structure, then you can use the `mzn-bench collect-instances`
   command:
   ```bash
   mzn-bench collect-instances <directory> > instances.csv
   ```
2. Instantiate a benchmarking environment. This environment should at least
   contain a Python virtual environment with _mzn-bench_ and your benchmarking
   scripts, but you can also set up environmental variables, like `PATH`, and
   load cluster modules. The following script, `bench_env.sh`,
   provides an example environment that can be loaded using `source bench_env.sh`:

   ```bash
   if [[ "${BASH_SOURCE[0]}" = "${0}" ]]; then
       >&2 echo "Remember: you need to run me as 'source ${0}', not execute it!"
       exit
   fi

   # Create or activate Python virtual environment
   if [ -d venv ]; then
       source venv/bin/activate
   else
      python3 -m venv venv
       source venv/bin/activate
       python3 -m pip install mzn-bench
   fi

   # Set other environment variables and load cluster modules
   module load MiniZinc/2.4.3
   ```

3. Create a benchmarking script. This script will contain the configuration of
   where the instance file is located, what MiniZinc/Solver configurations to
   run for every instance, and how the benchmark runner itself should be
   configured. The script mainly consists of a call to `schedule` in
   `mzn_bench`. For example a benchmarking script that runs Gecode and
   Chuffed for 20 minutes might look like this:

   ```python
   from datetime import timedelta
   from pathlib import Path

   import minizinc

   from mzn_bench import Configuration, schedule

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
- `debug: bool = False` - Directly capture the output of individual jobs
  and store them in a `./logs/` directory.
- `wait: bool = False` - The scheduling process will wait for all jobs to
  finish.

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
- `optimisation_level: Optional[int] = None` - MiniZinc compilation
  optimisation level, e.g., `-O3`.
- `other_flags: Dict[str, Any] = field(default_factory=dict)` - A mapping of
  flag name to value of other flags to be provided to the compiler/solver
- `extra_data: Dict[str, Any] = field(default_factory=dict)` - Extra data to be
  added when using a specific Configuration. Internally this will be used by
  MiniZinc Python's `__setitem__` method on the generated instances. If data
  needs the value of an identifier internal to MiniZinc, then please use an
  `DZNExpression` object (e.g., `{"preferred_encoding": DZNExpression("UNARY")}`).

## Schedule SLURM jobs

The job now has to be started on the cluster with the right number of tasks
(one for every instance/solver combination). Luckily, the benchmarking script
that you've created in the previous step should take care of all of this.
So once we ensure that our environment is ready for ou benchmark, we can
execute our script and our job will be scheduled.

For example, if we had created a script `bench_env.sh` with our benchmarking
environment and a script `start_bench.py` with our `schedule` call, then the
following code should schedule our job:

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
are not expected to work unless this package is installed as
`pip install mzn-bench[scripts]`.
This allows us to install a minimal version on the running cluster and this
more complete version locally while processing the data.

### General aggregation

The following scripts can help gather the raw `*_stats.yml`/`*_sol.yml` files
and combine them for further use:

- `mzn-bench collect-objectives <result_dir> <objectives.csv>` -
  This script gathers all objective value information given by MiniZinc and the
  used solvers and combines it into a single CSV file.
- `mzn-bench collect-statistics <result_dir> <statistics.csv>` -
  This script gathers all statistical information given by MiniZinc and the used
  solvers and combines it into a single CSV file.

### Tabulation

The following scripts filter and tabulate specific statistics.

- `mzn-bench report-status <statistics.csv>` - This command will report the
  number of occurrences of the various solving status of your MiniZinc tasks.
  Please consult the `-h` flag to display all options.
- `mzn-bench compare-configurations <statistics.csv> <before_conf> <after_conf>` - This command reports on the differences of the achieved
  results between two configurations (differences in status, runtime, and
  objective). You can adjust the changes deemed significant with the
  `--time-delta` and `--objective-delta` flag. You can use the `--output-mode json` option to ensure the output can be easily parsed by other programs.

### Solution checking

The `mzn-bench check-solutions` command takes the solutions output during run
and feeds them back into the model to check that the result is satisfiable.
It also stores the objective and satisfiability information to be used when
checking statuses. The `-c` option can be used to set how many solutions
to check (zero to check all solutions).

```bash
# Check three solutions from each instance
mzn-bench check-solutions -c 3 ./results
```

This requires the problem `.mzn` and `.dzn` files from the benchmark run to be
available in order to run the checker. The `--base-dir <DIR>` option can be used
to specify a root directory relative to which the file names in the
`*_sol.yml` files are resolved.

### Status checking

The `mzn-bench check-statuses` command takes the results from `check-solutions`
command above (which must be run first) and then checks for any solvers which
have either

- Falsely claimed optimality - where optimality was found by a solver, but a
  better objective was found elsewhere and verified to be correct.
- Falsely claimed unsatisfiability - where unsatisfiability was found by a
  solver, but another solver has given a correct solution for the instance.

### Graph generation

There are a number of plotting helper functions available in
`mzn_bench.analysis.plot`. In order to use these, you must enable the
plotting features with `pip install mzn-bench[plotting]`. These use the
[Bokeh](https://bokeh.org/) visualisation library to provide interactive plots.

The `read_csv` function returns a tuple of [pandas](https://pandas.pydata.org/)
data frames containing objective and statistics data for plotting or further
data analysis.

```py
from mzn_bench.analysis.collect import read_csv
from mzn_bench.analysis.plot import plot_all_instances
from bokeh.plotting import show

# Read CSVs generated by mzn-bench collect-result as pandas dataframes
objs, stats = read_csv("objectives.csv", "statistics.csv")

# Grid plot giving objective values over time, or time to solve
# (depending on instance type)
show(plot_all_instances(objs, stats))
```
