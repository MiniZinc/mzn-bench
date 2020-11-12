#!/usr/bin/env python3
import asyncio
import csv
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field, fields
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, NoReturn, Optional

import minizinc
import ruamel.yaml


@dataclass
class Configuration:
    name: str
    solver: minizinc.Solver
    minizinc: Optional[Path] = None
    processes: Optional[int] = None
    random_seed: Optional[int] = None
    free_search: bool = False
    optimisation_level: Optional[int] = None
    other_flags: Dict[str, Any] = field(default_factory=dict)
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        obj = asdict(self)
        obj["solver"] = self.solver.output_configuration()
        obj["sol_ident"] = self.solver._identifier
        if self.minizinc is not None:
            obj["minizinc"] = str(self.minizinc)
        return obj

    @classmethod
    def from_dict(cls, obj):
        field_names = set(f.name for f in fields(minizinc.Solver))
        obj["solver"] = minizinc.Solver(
            **{k: v for k, v in json.loads(obj["solver"]).items() if k in field_names}
        )
        obj["solver"]._identifier = obj.pop("sol_ident")
        if obj["minizinc"] is not None:
            obj["minizinc"] = Path(obj["minizinc"])
        return cls(**obj)


@dataclass
class DZNExpression:
    expr: str

    def __init__(self, dzn_expr: str):
        self.expr = dzn_expr


class _JSONEnc(minizinc.json.MZNJSONEncoder):
    def default(self, o):
        if isinstance(o, DZNExpression):
            return {"_mzn_slurm_dzn_expr": o.expr}
        return super().default(o)


class _JSONDec(minizinc.json.MZNJSONEncoder):
    def object_hook(self, obj):
        if len(obj) == 1 and "_mzn_slurm_dzn_expr" in obj:
            return minizinc.model.UnknownExpression(obj["_mzn_slurm_dzn_expr"])
        return super().object_hook(obj)


# Schedule SLURM tasks
def schedule(
    instances: Path,
    timeout: timedelta,
    configurations: Iterable[Configuration],
    nodelist: Iterable[str],
    output_dir: Path = Path.cwd() / "results",
    job_name: str = "MiniZinc Benchmark",
    cpus_per_task: int = 1,
    memory: int = 4096,
    debug_slurm: bool = False,
    nice: Optional[int] = None,
) -> NoReturn:

    # Count number of instances
    assert instances.exists()
    num_instances = sum(1 for line in instances.open()) - 1

    # Create output_dir if it does not exist
    output_dir.mkdir(parents=True, exist_ok=True)

    slurm_output = "/dev/null"
    if debug_slurm:
        slurm_output = f"{output_dir.resolve()}/minizinc_slurm-%A_%a.out"

    # Locate this script
    this_script = Path(os.path.realpath(__file__))

    # Setup environment to run the script
    env = os.environ.copy()
    env["MZN_SLURM_CONFIGS"] = json.dumps(
        [conf.to_dict() for conf in configurations], cls=_JSONEnc
    )
    env["MZN_SLURM_TIMEOUT"] = str(int(timeout / timedelta(milliseconds=1)))

    cmd = [
        "sbatch",
        f"--output={slurm_output}",
        f'--job-name="{job_name}"',
        f"--cpus-per-task={cpus_per_task}",
        f"--mem={memory}",
        f"--nodelist={','.join(nodelist)}",
        f"--array=1-{num_instances*len(configurations)}",
        f"--time={timeout + timedelta(minutes=1)}",  # Set hard timeout as failsafe
    ]
    if nice is not None:
        cmd.append(f"--nice={nice}")
    cmd.extend(
        [
            str(this_script.resolve()),
            str(instances.resolve()),
            str(output_dir.resolve()),
        ]
    )

    # Replace current process with the correct sbatch call
    os.execvpe(
        "sbatch",
        cmd,
        env,
    )


async def run_instance(
    problem, model, data, config, timeout, stat_base, sol_file, stats_file
):
    statistics = stat_base.copy()
    try:
        driver = minizinc.default_driver
        if config.minizinc is not None:
            driver = minizinc.CLI.CLIDriver(config.minizinc)
        instance = minizinc.Instance(config.solver, minizinc.Model(model), driver)
        if data is not None:
            instance.add_file(data, parse_data=False)
        is_satisfaction = instance.method == minizinc.Method.SATISFY

        for key, value in config.extra_data.items():
            instance[key] = value

        start = time.perf_counter()
        with sol_file.open(mode="w") as file:
            async for result in instance.solutions(
                timeout=timeout,
                processes=config.processes,
                random_seed=config.random_seed,
                intermediate_solutions=True,
                free_search=config.free_search,
                optimisation_level=config.optimisation_level,
                **config.other_flags,
            ):
                solution = stat_base.copy()
                solution["status"] = str(result.status)
                if "time" in result.statistics:
                    solution["time"] = result.statistics.pop("time").total_seconds()
                if result.solution is not None:
                    solution["solution"] = asdict(result.solution)
                    solution["solution"].pop("_output_item", None)
                    solution["solution"].pop("_checker", None)
                file.write(ruamel.yaml.dump([solution]))

                statistics.update(result.statistics)
                statistics["status"] = str(result.status)
                if result.solution is not None and not is_satisfaction:
                    statistics["objective"] = result.solution.objective

        total_time = time.perf_counter() - start
        statistics["time"] = total_time
    except minizinc.MiniZincError as err:
        statistics["status"] = str(minizinc.result.Status.ERROR)
        statistics["error"] = str(err)

    for key, val in statistics.items():
        if isinstance(val, timedelta):
            statistics[key] = val.total_seconds()
    ruamel.yaml.dump(
        statistics,
        stats_file.open(mode="w"),
        default_flow_style=False,
    )


if __name__ == "__main__":
    filename = "minizinc_slurm"
    output_dir = Path.home()
    try:
        instances = Path(sys.argv[1])
        output_dir = Path(sys.argv[2])
        task_id = int(os.environ["SLURM_ARRAY_TASK_ID"]) - 1
        timeout = timedelta(milliseconds=int(os.environ["MZN_SLURM_TIMEOUT"]))
        configurations = [
            Configuration.from_dict(conf)
            for conf in json.loads(os.environ["MZN_SLURM_CONFIGS"], cls=_JSONDec)
        ]

        # Select instance and configuration based on SLURM_ARRAY_TASK_ID
        with open(instances) as instances_file:
            reader = csv.reader(instances_file, dialect="unix")
            next(reader)  # Skip the header line
            row = 1
            while task_id >= len(configurations):
                next(reader)  # Skip non-selected instances
                task_id = task_id - len(configurations)
                row = row + 1
            selected_instance = next(reader)
            config = configurations[task_id]
            filename = f"{row}_{config.name}"

        # Process instance
        problem = selected_instance[0]

        model = Path(selected_instance[1])
        if not model.is_absolute():
            model = instances.parent / model

        data = None
        if selected_instance[2] != "":
            data = Path(selected_instance[2])
            if not data.is_absolute():
                data = instances.parent / data

        stat_base = {
            "problem": selected_instance[0],
            "model": selected_instance[1],
            "data_file": selected_instance[2],
            "configuration": config.name,
            "status": str(minizinc.result.Status.UNKNOWN),
        }

        # Run instance
        asyncio.run(
            run_instance(
                problem,
                model,
                data,
                config,
                timeout,
                stat_base,
                output_dir / f"{filename}_sol.yml",
                output_dir / f"{filename}_stats.yml",
            )
        )
    except Exception:
        file = output_dir / f"{filename}_err.txt"
        file.write_text(f"ERROR: {traceback.format_exc()}")
