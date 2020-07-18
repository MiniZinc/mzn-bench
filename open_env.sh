#!/usr/bin/env bash

# This script should be sourced, `source open_env.sh`, to enter the python
# virtual environment used for MiniZinc Python. If the environment is not yet
# present, then it will be created.

if [[ "${BASH_SOURCE[0]}" = "${0}" ]]; then
    >&2 echo "Remember: you need to run me as 'source ./open_env.sh', not execute it!"
    exit
fi

if [ -d venv ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
    python3 -m pip install minizinc pandas
fi
mkdir -p results

# load cluster modules
module load MiniZinc/2.4.3
