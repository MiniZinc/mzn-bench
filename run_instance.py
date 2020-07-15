#!/usr/bin/env python3
import asyncio
import config
import csv
import minizinc
import os
import sys
import traceback

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

    with open(f"{filename}_sol.csv", "w") as file:
        keys = ["problem", "model", "data_file", "solver", "time", "status", "objective"]
        writer_sol = csv.writer(file, dialect="unix")
        writer_sol.writerow(keys)

        async for result in instance.solutions(
            timeout=config.timeout,
            processes=config.processes,
            random_seed=config.random_seed,
            intermediate_solutions=True,
            free_search=config.free_search,
            # optimisation_level=config.optimisation_level,
        ):
            status = result.status
            statistics.update(result.statistics)
            objective = ""
            if not is_satisfaction and result.solution is not None:
                objective = result.solution.objective
            writer_sol.writerow(row + [solver.id + "@" + solver.version, result.statistics.get("time", ""), result.status, objective])

    with open(f"{filename}_stats.csv", "w") as file:
        keys = list(
            set(
                ["problem", "model", "data_file", "status"]
                + list(minizinc.result.StdStatisticTypes.keys())
                + list(statistics.keys())
            )
        )
        writer_stat = csv.DictWriter(
            file, keys, dialect="unix", extrasaction="ignore"
        )
        writer_stat.writeheader()
        writer_stat.writerow(statistics)


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
