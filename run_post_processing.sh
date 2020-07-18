#!/usr/bin/env bash

#SBATCH --job-name=minibench-pp
#SBATCH --cpus-per-task=1
#SBATCH --mem=4096
#SBATCH --nodelist=critical001

source open_env.sh
python run_post_processing.py
