# MiniZinc SLURM

This is a small collection of scripts that allow you to run benchmarks on a set
of MiniZinc instance using MiniZinc Python. The process is split into several
steps to be easily customisable to different kinds of possible benchmarks.

# Preparation

1. Create a CSV file for the MiniZinc instances containing *problem*, *model*, *data_file*. If you store the instances in the MiniZinc benchmarks repository structure, then you can use the `collect_instances.py` script:
```
python collect_instances.py <directory> > instances.csv
```
2. Configure the MiniZinc Python behaviour using the `config.py` file
3. Ensure that MiniZinc and all the solvers in the configuration are available on the cluster nodes. Environment setup can be managed in the `open_env.sh` script.
3. Customise the SLURM settings in `run_instance.sh` to match the required settings from your server cluster.

# Schedule SLURM jobs

The job now has to be started on the cluster with the right number of tasks (one for every instance/solver combination). The `start_slurm.py` script will read the configuration from the previous step and call `sbatch` with the correct arguments:
```
./start_slurm.py
```

# Collect information

