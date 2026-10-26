#!/usr/bin/env python3
import asyncio
import csv
import json
import math
import os
import shutil
import signal
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field, fields
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, NoReturn, Optional
import minizinc
from ruamel.yaml import YAML

yaml = YAML(typ="safe")
yaml.register_class(minizinc.types.ConstrEnum)
yaml.register_class(minizinc.types.AnonEnum)
yaml.default_flow_style = False

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
    extra_model_files: List[Path] = field(default_factory=list)
    stage: Optional[bool] = None

    def to_dict(self):
        # Non-recursive version of `asdict`
        obj = {field.name: getattr(self, field.name) for field in fields(self)}
        if self.solver._identifier is not None:
            obj["solver"] = ""
            obj["sol_ident"] = self.solver._identifier
        else:
            obj["solver"] = self.solver.output_configuration()
            obj["sol_ident"] = ""
        if self.minizinc is not None:
            obj["minizinc"] = str(self.minizinc)
        if self.extra_model_files is not None:
            obj["extra_model_files"] = [str(f) for f in self.extra_model_files]
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
            obj["solver"] = minizinc.Solver.load(Path(identifier))
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
        if obj["extra_model_files"] is not None:
            obj["extra_model_files"] = [Path(f) for f in obj["extra_model_files"]]
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kwargs["object_hook"] = self.mzn_object_hook

    def mzn_object_hook(self, obj):
        if len(obj) == 1 and "_mzn_slurm_dzn_expr" in obj:
            return minizinc.model.UnknownExpression(obj["_mzn_slurm_dzn_expr"])
        return super().mzn_object_hook(obj)


# Schedule SLURM tasks
def schedule(
    instances: Path,
    timeout: timedelta,
    configurations: Iterable[Configuration],
    nodelist: Optional[Iterable[str]] = None,
    partition: Optional[Iterable[str]] = None,
    output_dir: Path = Path.cwd() / "results",
    job_name: str = "MiniZinc Benchmark",
    cpus_per_task: int = 1,
    memory: int = 4096,
    mem_per_cpu: bool = False,
    debug: bool = False,
    nice: Optional[int] = None,
    wait: bool = False,
    **kwargs,
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

    n_tasks = num_instances * len(configurations)
    instances = str(instances.resolve())
    output_dir = str(output_dir.resolve())

    if nodelist is None and partition is None:
        os.environ.update(env)
        for i in range(n_tasks):  # simulate environment like SLURM
            os.environ["SLURM_ARRAY_TASK_ID"] = str(i + 1)
            main(Path(instances), Path(output_dir))
        return
    cmd = [
        "sbatch",
        f"--output={slurm_output}",
        f"--job-name={job_name}",
        f"--cpus-per-task={cpus_per_task}",
        f"--mem-per-cpu={memory}" if mem_per_cpu else f"--mem={memory}",
        f"--array=1-{n_tasks}",
        # Set hard timeout (in minutes) as failsafe, with extra time to stage files
        f"--time={math.ceil((timeout + timedelta(minutes=3)) / timedelta(minutes=1))}",
    ]
    if nodelist is not None:
        cmd += [
            f"--nodelist={','.join(nodelist)}",
        ]
    if partition is not None:
        cmd += [
            f"--partition={','.join(partition)}",
        ]
    if nice is not None:
        cmd.append(f"--nice={nice}")
    if wait:
        cmd.append("--wait")
    for option, value in kwargs.items():
        cmd.append(f"--{option.replace('_', '-')}={value}")
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
    problem,
    model_files,
    data,
    config,
    timeout,
    stat_base,
    sol_file,
    stats_file,
    stage_time=None,
):
    statistics = stat_base.copy()
    if stage_time is not None:
        statistics["stage_time"] = stage_time
    start = time.perf_counter()
    try:
        driver = minizinc.default_driver
        if config.minizinc is not None:
            assert config.minizinc.exists()
            driver = minizinc.Driver(config.minizinc)
        assert len(model_files) > 0
        model = minizinc.Model(model_files + config.extra_model_files)
        model.output_type = dict
        instance = minizinc.Instance(config.solver, model, driver)
        for path in data:
            instance.add_file(path, parse_data=False)
        is_satisfaction = instance.method == minizinc.Method.SATISFY

        for key, value in config.extra_data.items():
            instance[key] = value

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
                    statistics_time = result.statistics.pop("time")
                    if type(statistics_time) is timedelta:
                        solution["time"] = (
                            statistics_time.total_seconds()
                        )  # convert timedelta to seconds (float), since we cannot register and serialize it to YAML
                    else:
                        raise TypeError(
                            f"Time statistic was not `datetime.timedelta` type, but was {type(statistics_time)}. Perhaps you are using an older version of minizinc-python"
                        )
                if result.solution is not None:
                    solution["solution"] = result.solution
                    solution["solution"].pop("_output_item", None)
                    solution["solution"].pop("_checker", None)
                yaml.dump([solution], file)

                if "objective" in result.statistics:
                    result.statistics["solver_objective"] = result.statistics.pop(
                        "objective"
                    )
                statistics.update(result.statistics)
                statistics["status"] = str(result.status)
                if result.solution is not None and not is_satisfaction:
                    statistics["objective"] = result.solution["objective"]
    except minizinc.MiniZincError as err:
        statistics["status"] = str(minizinc.result.Status.ERROR)
        statistics["error"] = str(err)

    statistics["time"] = time.perf_counter() - start

    for key, val in statistics.items():
        if isinstance(val, timedelta):
            statistics[key] = val.total_seconds()

    with open(stats_file, "w") as file:
        yaml.dump(statistics, file)


# Installations that are not a self-contained MiniZinc bundle
_SYSTEM_PREFIXES = [
    "/",
    "/usr",
    "/usr/local",
    "/opt",
    "/opt/local",
    "/opt/homebrew",
    "~",
    "~/.local",
]


# Not an `Exception`, so that asyncio does not catch it in a callback
class _Terminated(SystemExit):
    pass


def _terminate(signum, frame):
    raise _Terminated("Received SIGTERM (e.g., SLURM time limit)")


def _stage(
    stage_dir: Path,
    executable: Optional[Path],
    model_files: List[Path],
    data: List[Path],
):
    """Copy the MiniZinc bundle, the `model_files` and the other `.mzn` files in
    their directories, and the `data` files to `stage_dir`.

    Returns the path of the copied executable (or the original if it is not part
    of a bundle) and the paths of the copied model and data files."""
    if executable is not None:
        # Linux bundle: <root>/bin/minizinc, macOS app: <root>/Resources/minizinc
        exe = executable.resolve()
        root = exe.parent.parent
        share = [root / "share" / "minizinc", root / "Resources" / "share" / "minizinc"]
        # Do not copy a full system, conda, or Spack prefix
        prefixes = {Path(p).expanduser().resolve() for p in _SYSTEM_PREFIXES}
        is_prefix = root in prefixes or any(
            (root / d).exists() for d in ["conda-meta", ".spack"]
        )
        if any(d.is_dir() for d in share) and not is_prefix:
            shutil.copytree(root, stage_dir / root.name, symlinks=True)
            executable = stage_dir / root.name / exe.relative_to(root)
        else:
            print(f"WARNING: {exe} is not part of a MiniZinc bundle", file=sys.stderr)

    # Copy the files at the same relative location. Model files can include
    # other models in their directory, data files cannot include files.
    def dest(f: Path) -> Path:
        return stage_dir / "files" / f.absolute().relative_to(f.anchor)

    for d in {f.parent for f in model_files}:
        dest(d).mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.mzn"):
            shutil.copy2(f, dest(f))
    for f in model_files + data:
        dest(f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest(f))
    return executable, [dest(f) for f in model_files], [dest(f) for f in data]


def main(instances, output_dir):
    filename = "minizinc_slurm"
    stage_dir = None
    prev_driver = minizinc.default_driver
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

        model_files = []
        for file in selected_instance[1].split(":"):
            if file != "":
                path = Path(file)
                if not path.is_absolute():
                    path = instances.parent / path
                model_files.append(path)

        data = []
        for file in selected_instance[2].split(":"):
            if file != "":
                path = Path(file)
                if not path.is_absolute():
                    path = instances.parent / path
                data.append(path)

        stat_base = {
            "problem": selected_instance[0],
            "model": selected_instance[1],
            "data_file": selected_instance[2],
            "configuration": config.name,
            "status": str(minizinc.result.Status.UNKNOWN),
        }

        # Copy MiniZinc and the instance files to the (local) $TMPDIR
        result_dir = output_dir
        stage_time = None
        if config.stage or (
            config.stage is None
            and "SLURM_JOB_ID" in os.environ
            and os.environ.get("TMPDIR")
        ):
            start = time.perf_counter()
            stage_dir = Path(tempfile.mkdtemp(prefix="mzn_bench_"))  # Uses $TMPDIR
            result_dir = stage_dir
            # The default driver is the driver of `config.minizinc` (see above)
            driver = minizinc.default_driver
            executable = None if driver is None else driver.executable
            staged, model_files, data = _stage(stage_dir, executable, model_files, data)
            # Start the copied driver here, outside of the timed part
            if staged != executable:
                minizinc.Driver(staged).make_default()
                config.minizinc = None
            stage_time = time.perf_counter() - start

        # Run instance
        asyncio.run(
            run_instance(
                problem,
                model_files,
                data,
                config,
                timeout,
                stat_base,
                result_dir / f"{filename}_sol.yml",
                result_dir / f"{filename}_stats.yml",
                stage_time,
            )
        )
    except (Exception, _Terminated):
        if "SLURM_JOB_NODELIST" not in os.environ:
            raise
        file = output_dir / f"{filename}_err.txt"
        file.write_text(f"ERROR: {traceback.format_exc()}")
    finally:
        if signal.getsignal(signal.SIGTERM) is _terminate:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)  # Do not stop the clean up
        minizinc.default_driver = prev_driver
        if stage_dir is not None:
            try:
                for name in [f"{filename}_sol.yml", f"{filename}_stats.yml"]:
                    if (stage_dir / name).exists():
                        tmp = output_dir / f"{name}.tmp"
                        shutil.copyfile(stage_dir / name, tmp)
                        tmp.replace(output_dir / name)
            finally:
                shutil.rmtree(stage_dir, ignore_errors=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)  # SLURM sends SIGTERM at the time limit
    instances = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else Path.home()
    main(instances, output_dir)
