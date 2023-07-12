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
from typing import Any, Dict, Iterable, NoReturn, Optional
import minizinc
from ruamel.yaml import YAML

yaml=YAML(typ="unsafe", pure=True)

if os.environ.get("MZN_DEBUG", "OFF") == "ON":
    import logging

    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)



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
        if self.solver._identifier is not None:
            obj["solver"] = ""
            obj["sol_ident"] = self.solver._identifier
        else:
            obj["solver"] = self.solver.output_configuration()
            obj["sol_ident"] = ""
        if self.minizinc is not None:
            obj["minizinc"] = str(self.minizinc)
        return obj

    @classmethod
    def from_dict(cls, obj):
        field_names = set(f.name for f in fields(minizinc.Solver))
        identifier = obj.pop("sol_ident")
        if identifier == "":
            obj["solver"] = minizinc.Solver(
                **{
                    k: v
                    for k, v in json.loads(obj["solver"]).items()
                    if k in field_names
                }
            )
        elif identifier.endswith(".msc"):
            obj["solver"] = minizinc.Solver.load(identifier)
        else:
            # TODO: version tags should be handled correctly by MiniZinc Python
            version = None
            if "@" in identifier:
                split = identifier.split("@")
                assert len(split) == 2
                identifier = split[0]
                version = split[1]
            obj["solver"] = minizinc.Solver.lookup(identifier)
            if version is not None:
                assert obj["solver"].version == version

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


class _JSONDec(minizinc.json.MZNJSONDecoder):
    def object_hook(self, obj):
        if len(obj) == 1 and "_mzn_slurm_dzn_expr" in obj:
            return minizinc.model.UnknownExpression(obj["_mzn_slurm_dzn_expr"])
        return super().object_hook(obj)


# Schedule SLURM tasks
def schedule(
    instances: Path,
    timeout: timedelta,
    configurations: Iterable[Configuration],
    nodelist: Optional[Iterable[str]] = None,
    output_dir: Path = Path.cwd() / "results",
    job_name: str = "MiniZinc Benchmark",
    cpus_per_task: int = 1,
    memory: int = 4096,
    debug: bool = False,
    nice: Optional[int] = None,
    wait: bool = False,
) -> NoReturn:
    # Count number of instances
    assert instances.exists()
    num_instances = sum(1 for line in instances.open()) - 1

    # Create output_dir if it does not exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Locate this script
    this_script = Path(os.path.realpath(__file__))

    # Setup environment to run the script
    env = os.environ.copy()
    env["MZN_SLURM_CONFIGS"] = json.dumps(
        [conf.to_dict() for conf in configurations], cls=_JSONEnc
    )
    env["MZN_SLURM_TIMEOUT"] = str(int(timeout / timedelta(milliseconds=1)))

    slurm_output = "/dev/null"
    if debug:
        slurm_output = f"{output_dir.resolve()}/minizinc_slurm-%A_%a.out"
        env["MZN_DEBUG"] = "ON"

    n_tasks = num_instances*len(configurations)
    instances = str(instances.resolve())
    output_dir = str(output_dir.resolve())

    if nodelist is None:
        os.environ.update(env)
        for i in range(n_tasks):  # simulate environment like SLURM
            os.environ["SLURM_ARRAY_TASK_ID"] = str(i+1)
            main(Path(instances), Path(output_dir))
        return
    cmd = [
        "sbatch",
        f"--output={slurm_output}",
        f'--job-name="{job_name}"',
        f"--cpus-per-task={cpus_per_task}",
        f"--mem={memory}",
        f"--nodelist={','.join(nodelist)}",
        f"--array=1-{n_tasks}",
        f"--time={timeout + timedelta(minutes=1)}",  # Set hard timeout as failsafe
    ]
    if nice is not None:
        cmd.append(f"--nice={nice}")
    if wait:
        cmd.append(f"--wait")
    cmd.extend(
        [
            str(this_script.resolve()),
            str(instances),
            str(output_dir),
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
            assert config.minizinc.exists()
            driver = minizinc.Driver(config.minizinc)
        model=minizinc.Model(model)
        model.output_type = dict
        instance = minizinc.Instance(config.solver, model, driver)
        for path in data:
            instance.add_file(path, parse_data=False)
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
                    solution["time"] = result.statistics.pop("time")
                if result.solution is not None:
                    solution["solution"] = result.solution
                    solution["solution"].pop("_output_item", None)
                    solution["solution"].pop("_checker", None)
                yaml.dump([solution], file)

                statistics.update(result.statistics)
                statistics["status"] = str(result.status)
                if result.solution is not None and not is_satisfaction:
                    statistics["objective"] = result.solution["objective"]

        total_time = time.perf_counter() - start
        statistics["time"] = total_time
    except minizinc.MiniZincError as err:
        statistics["status"] = str(minizinc.result.Status.ERROR)
        statistics["error"] = str(err)

    for key, val in statistics.items():
        if isinstance(val, timedelta):
            statistics[key] = val.total_seconds()
    yaml.dump(
        statistics,
        stats_file.open(mode="w"),
        # default_flow_style=False,  # TODO does not seem to be supported anymore?
    )


def main(instances, output_dir):
    filename = "minizinc_slurm"
    try:
        task_id = int(os.environ["SLURM_ARRAY_TASK_ID"]) - 1
        timeout = timedelta(milliseconds=int(os.environ["MZN_SLURM_TIMEOUT"]))
        configurations = json.loads(os.environ["MZN_SLURM_CONFIGS"], cls=_JSONDec)

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

        # Deserialise Configuration
        config = configurations[task_id]
        # TODO: workaround because we might not know the solver in the system MiniZinc
        if config["minizinc"] is not None:
            mzn_path = Path(config["minizinc"])
            assert mzn_path.exists()
            minizinc.Driver(mzn_path).make_default()
        config = Configuration.from_dict(config)

        filename = f"{row}_{config.name}"

        # Process instance
        problem = selected_instance[0]

        model = Path(selected_instance[1])
        if not model.is_absolute():
            model = instances.parent / model

        data = []
        for file in selected_instance[2].split(":"):
            if file != "":
                path = Path(selected_instance[2])
                if not path.is_absolute():
                    path = instances.parent / file
                data.append(path)

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
        if "SLURM_JOB_NODELIST" not in os.environ:
            raise
        file = output_dir / f"{filename}_err.txt"
        file.write_text(f"ERROR: {traceback.format_exc()}")

if __name__ == "__main__":
    instances = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else Path.home()
    main(instances, output_dir)

