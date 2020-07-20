# MiniZinc SLURM

This is a small collection of scripts that allow you to run benchmarks on a set
of MiniZinc instance using MiniZinc Python. The process is split into several
steps to be easily customisable to different kinds of possible benchmarks.

**IMPORTANT:** All the scripts described in the following steps assume you have
activated the python environment using `source open_env.sh`. This file can also
be used to set the correct environmental variables, like `export
PATH=$HOME/bin:$PATH`, or load cluster modules, like `module load
MiniZinc/2.4.3`. Ensure you source the file again after changing it.

# Preparation

1. Create a CSV file for the MiniZinc instances containing *problem*, *model*,
   *data_file*. If you store the instances in the MiniZinc benchmarks
   repository structure, then you can use the `collect_instances.py` script:
```
python collect_instances.py <directory> > instances.csv
```
2. Configure the MiniZinc configurations, solvers, and SLURM behaviour in the
   `minizinc_slurm.py` file.

# Schedule SLURM jobs

The job now has to be started on the cluster with the right number of tasks
(one for every instance/solver combination). The `minizinc_slurm.py` script
will read its configuration and call `sbatch` with the correct arguments:
```
./minizinc_slurm.py
```

# Collect information

