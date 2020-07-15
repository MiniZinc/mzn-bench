#!/usr/bin/env bash

# Note that this scipt should be called using `sbatch --array=1-x run_instance.sh` where `x` is the number of instances times the number of solvers

# Configure me to match your node requirements
#SBATCH --job-name=minibench
#SBATCH --cpus-per-task=1
#SBATCH --mem=4096
#SBATCH --nodelist=critical001

if [ -z ${SLURM_ARRAY_TASK_ID} ]; then
  >&2 echo "ERROR: This script can only be used as part of a SLURM array job"
  exit 1
fi

source open_env.sh
python run_instance.py ${SLURM_ARRAY_TASK_ID}
