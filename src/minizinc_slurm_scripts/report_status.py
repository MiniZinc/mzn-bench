#!/usr/bin/env python3
import argparse
import csv
import os
import sys

from pathlib import Path
from tabulate import tabulate, tabulate_formats

parser = argparse.ArgumentParser(
    description="Aggregate status of MiniZinc instance runs into a table"
)
parser.add_argument(
    "statistics",
    metavar="statistics.csv",
    type=Path,
    help="The aggregated statistics file",
)
parser.add_argument(
    "--per-model",
    dest="per_model",
    action="store_const",
    const=True,
    default=False,
    help="Create a row for every model",
)
parser.add_argument(
    "--per-problem",
    dest="per_problem",
    action="store_const",
    const=True,
    default=False,
    help="Create a row for every problem",
)
parser.add_argument(
    "--avg-time",
    dest="avg_time",
    action="store_const",
    const=True,
    default=False,
    help="Show average runtime in the table",
)
parser.add_argument(
    "--output-mode",
    dest="mode",
    choices=tabulate_formats,
    default="pretty",
    help="The table format used in the output. All valid tablefmt values are allow, try `latex` for example.",
)


args = parser.parse_args()

keys = ["configuration"]
if args.per_model:
    keys.append("model")
if args.per_problem:
    keys.append("problem")

seen_status = set()
table = {}
with args.statistics.open() as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        key = [row["configuration"]]
        if args.per_model:
            key.append(row["model"])
        if args.per_problem:
            key.append(row["problem"])

        seen_status.add(row["status"])
        key = tuple(key)
        time = float(row["time"])
        if key not in table:
            table[key] = {row["status"]: [time]}
        elif row["status"] not in table[tuple(key)]:
            table[key][row["status"]] = [time]
        else:
            table[key][row["status"]].append(time)

seen_status = list(seen_status)
seen_status.sort(reverse=True)

print(
    tabulate(
        [
            list(key)
            + [
                f"{len(row[s])} ({sum(row[s]) / len(row[s]) :.2f}s)"
                if args.avg_time and s in row
                else str(len(row.get(s, [])))
                for s in seen_status
            ]
            for key, row in table.items()
        ],
        headers=(keys + seen_status),
        tablefmt=args.mode,
    )
)
