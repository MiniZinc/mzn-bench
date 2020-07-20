#!/usr/bin/env python3
import asyncio
import config
import csv
import dataclasses
import minizinc
import os
import ruamel.yaml
import sys
import traceback

from datetime import timedelta
from pathlib import Path


# Instances Selection (File location)
if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <jobnr>")
    exit(1)

jobnr = int(sys.argv[1]) - 1
solver = None
filename = "noname"

async def solve_async(row):
    instance = minizinc.Instance(solver, minizinc.Model(Path(row[1])))
    if row[2] != "":
        instance.add_file(row[2], parse_data=False)
    is_satisfaction = (instance.method == minizinc.Method.SATISFY)

    statistics = {
        "problem": row[0],
        "model" : row[1],
        "data_file": row[2],
    }

    with Path(f"{filename}_sol.yml").open(mode="w") as file:
        async for result in instance.solutions(
            timeout=config.timeout,
            processes=config.processes,
            random_seed=config.random_seed,
            intermediate_solutions=True,
            free_search=config.free_search,
            # optimisation_level=config.optimisation_level,
        ):
            solution = {
                "problem": row[0],
                "model" : row[1],
                "data_file": row[2],
                "status": str(result.status),
            }
            if "time" in result.statistics:
                solution["time"] = result.statistics.pop("time").total_seconds()
            if result.solution is not None:
                solution["solution"] = dataclasses.asdict(result.solution)
                solution["solution"].pop("_output_item", None)
                solution["solution"].pop("_checker", None)
            file.write(ruamel.yaml.dump([solution]))

            statistics.update(result.statistics)

    for key, val in statistics.items():
        if isinstance(val, timedelta):
            statistics[key] = val.total_seconds()
    ruamel.yaml.dump(statistics, Path(f"{filename}_stats.yml").open(mode="w"), default_flow_style=False)


try:
    with open(config.instances) as instances_file:
        reader = csv.reader(instances_file, dialect="unix")
        next(reader)  # Skip the header line
        row = 1
        while jobnr >= len(config.solvers):
            next(reader)  # Skip non-selected instances
            jobnr = jobnr - len(config.solvers)
            row = row + 1
        selected_instance = next(reader)
        solver = config.solvers[jobnr]
        filename = f"results/{row}_{solver.id}_{solver.version.replace('.', '_')}"

        # Run instance
        asyncio.run(solve_async(selected_instance))
except Exception:
    file = Path(f"{filename}_err.txt")
    file.write_text(f"ERROR: {traceback.format_exc()}")
