#!/usr/bin/env python3
import asyncio
import csv
import dataclasses
import minizinc
import minizinc_slurm
import os
import ruamel.yaml
import sys
import traceback

from datetime import timedelta
from pathlib import Path

async def solve_async(row, config):
    instance = minizinc.Instance(config.solver, minizinc.Model(Path(row[1])))
    if row[2] != "":
        instance.add_file(row[2], parse_data=False)
    is_satisfaction = (instance.method == minizinc.Method.SATISFY)

    statistics = {
        "problem": row[0],
        "model" : row[1],
        "data_file": row[2],
        "configuration": config.name,
    }

    with (minizinc_slurm.output_dir / f"{filename}_sol.yml").open(mode="w") as file:
        async for result in instance.solutions(
            timeout=minizinc_slurm.timeout,
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
                "configuration": config.name,
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
    ruamel.yaml.dump(statistics, (minizinc_slurm.output_dir / f"{filename}_stats.yml").open(mode="w"), default_flow_style=False)

if __name__ == "__main__":
    filename = "noname"
    try:
        # Select instance based on 
        task_id = int(os.environ["SLURM_ARRAY_TASK_ID"]) - 1
        selected_instance = None
        with open(minizinc_slurm.instances) as instances_file:
            reader = csv.reader(instances_file, dialect="unix")
            next(reader)  # Skip the header line
            row = 1
            while task_id >= len(minizinc_slurm.configurations):
                next(reader)  # Skip non-selected instances
                task_id = task_id - len(minizinc_slurm.configurations)
                row = row + 1
            selected_instance = next(reader)
            config = minizinc_slurm.configurations[task_id]
            filename = f"{row}_{config.name}"

        # Run instance
        asyncio.run(solve_async(selected_instance, config))
    except Exception:
        file = minizinc_slurm.output_dir / f"{filename}_err.txt"
        file.write_text(f"ERROR: {traceback.format_exc()}")
