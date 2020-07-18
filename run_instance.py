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

statistics = {}
jobnr = int(sys.argv[1]) - 1
solver = None
extra_flags = {}
extra_data = None
filename = "noname"

async def solve_async(row):
    model = minizinc.Model(Path(row[1]))

    if extra_data is not None:
        model.add_string(extra_data)
    instance = minizinc.Instance(solver, model)
    if row[2] != "":
        instance.add_file(row[2], parse_data=False)
    is_satisfaction = (instance.method == minizinc.Method.SATISFY)

    statistics["problem"] = row[0]
    statistics["model"] = row[1]
    statistics["data_file"] = row[2]

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

            **extra_flags,

        ):
            status = result.status
            statistics.update(result.statistics)
            statistics["status"] = result.status
            if not is_satisfaction and result.solution is not None:
                statistics["objective"] = result.solution.objective
            writer_sol.writerow(row + [solver.id + "@" + solver.version, result.statistics.get("time", ""), result.status, statistics.get("objective", "")])

    with open(f"{filename}_stats.csv", "w") as file:
        # TODO to have a nicer order, a complete set of statistics keys should be sorted, and then duplicates should be removed without order distL
        keys = list(
                set(
                    ["problem", "model", "data_file", "status", "objective"]
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
        while jobnr >= len(config.runs):
            next(reader)  # Skip non-selected instances
            jobnr = jobnr - len(config.runs)
            row = row + 1
        selected_instance = next(reader)
        run = config.runs[jobnr]
        solver = run["solver"]
        alias = run.get("alias", "")
        extra_flags = run.get("extra_flags", {})
        extra_data = run.get("extra_data", None)


        statistics["row"] = row
        statistics["jobnr"] = jobnr
        statistics["alias"] = alias

        statistics["solver_id"] = solver.id
        statistics["solver_version"] = solver.version

        filename = f"results/{row}_{jobnr}_{alias}_{solver.id.replace('.', '_')}_{solver.version.replace('.', '_').replace('/', '_')}"

        # Run instance
        asyncio.run(solve_async(selected_instance))
except Exception:
    file = Path(f"{filename}_err.txt")
    file.write_text(f"ERROR: {traceback.format_exc()}")
