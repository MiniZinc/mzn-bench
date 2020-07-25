#!/usr/bin/env python3
"""This script collect MiniZinc instances and outputs them in a csv format

The MiniZinc instances are expected to be organised according to the MiniZinc
benchmarks structure:
    - Each problem is contained in its own folder
    - Problems contain one or more MiniZinc Model (.mzn) file
    - Each model is combined with all the data (.dzn / .json) in the same problem folder (and its subfolders)
    - If no data is found then it is assumed the model itself is an instance.

For convenience the script will print the number of collected instances on stderr.

Example usage:
    python collect_instances.py minizinc-benchmarks > instances.csv
"""
import csv
import os
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <folder>")
        exit(1)

    assert len(sys.argv) >= 2
    benchmarks_location = sys.argv[1]
    instances = 0

    writer = csv.writer(sys.stdout, dialect="unix")
    writer.writerow(("problem", "model", "data_file"))
    for root, _, files in os.walk(benchmarks_location):
        for name in files:
            if name.endswith(".mzn"):
                problem = root.split(os.sep)[-1]
                datafiles = 0
                for nroot, _, nfiles in os.walk(root):
                    for nname in nfiles:
                        if nname.endswith(".dzn") or nname.endswith(".json"):
                            datafiles = datafiles + 1
                            instances += 1
                            writer.writerow(
                                (
                                    problem,
                                    Path(root + "/" + name),
                                    Path(nroot + "/" + nname),
                                )
                            )

                if datafiles == 0:
                    instances += 1
                    writer.writerow((problem, Path(root + "/" + name), ""))

    print(f"Nr. Instances = {instances}", file=sys.stderr)


if __name__ == "__main__":
    main()
