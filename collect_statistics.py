#!/usr/bin/env python3
import csv
import glob
import os
import sys
from pathlib import Path

import ruamel.yaml

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <results_dir> <output.csv>")
    exit(1)


results = glob.iglob(sys.argv[1].rstrip(os.sep) + os.sep + "*_stats.yml")
output = Path(sys.argv[2])

statistics = []
keys = set()
for result in results:
    obj = ruamel.yaml.safe_load(Path(result).open())

    keys.update(obj.keys())
    statistics.append(obj)

with output.open(mode="w") as file:
    STANDARD = ["problem", "model", "data_file", "configuration", "status"]
    keys = keys.difference(STANDARD)
    writer = csv.DictWriter(
        file, STANDARD + list(keys), dialect="unix", extrasaction="ignore"
    )
    writer.writeheader()

    for stat in statistics:
        writer.writerow(stat)
