#!/usr/bin/env python3

import csv
import sys
from pathlib import Path
from typing import Iterable

import click

from mzn_bench.analysis.collect import collect_instances as collect_insts
from mzn_bench.analysis.collect import collect_objectives as collect_objs
from mzn_bench.analysis.collect import collect_statistics as collect_stats
from mzn_bench.analysis.collect import STANDARD_KEYS

IMPORT_ERROR = """This feature is not supported in minimal minizinc-slurm environments.

Please install using `pip install mzn-bench[scripts]`
"""

# Import the tabulate formats if the package is available
tabulate_options = []
try:
    from tabulate import tabulate_formats

    tabulate_options = tabulate_formats
except ImportError:
    pass


@click.group()
def main():
    """Command-line tool for minizinc-slurm."""
    pass


@main.command()
@click.argument("benchmarks_location", type=click.Path(exists=True, file_okay=True))
def collect_instances(benchmarks_location: str):
    """This script collect MiniZinc instances and outputs them in a csv format

    The MiniZinc instances are expected to be organised according to the MiniZinc
    benchmarks structure:
        - Each problem is contained in its own folder
        - Problems contain one or more MiniZinc Model (.mzn) file
        - Each model is combined with all the data (.dzn / .json) in the same problem folder (and its subfolders)
        - If no data is found then it is assumed the model itself is an instance.

    For convenience the script will print the number of collected instances on stderr.

    Example usage:
        mzn-bench collect-instances minizinc-benchmarks > instances.csv
    """
    instances = 0
    writer = csv.DictWriter(
        sys.stdout,
        ["problem", "model", "data_file"],
        dialect="unix",
    )
    writer.writeheader()
    for instance in collect_insts(benchmarks_location):
        writer.writerow(instance)
        instances += 1
    click.echo(f"Nr. Instances = {instances}", err=True)


@main.command()
@click.argument("dirs", nargs=-1, type=click.Path(exists=True, dir_okay=True))
@click.argument("out_file", nargs=1, type=click.Path(file_okay=True))
def collect_objectives(dirs: Iterable[str], out_file: str):
    """Collects objective values and combines them into a single CSV file.

    \b
    DIRS are directories containing the result YAML files
    OUT_FILE is the output CSV file containing objective data
    """

    count = 0
    with Path(out_file).open(mode="w") as file:
        writer = csv.DictWriter(
            file,
            STANDARD_KEYS + ["run", "objective"],
            dialect="unix",
            extrasaction="ignore",
        )
        writer.writeheader()
        last_keys = ("", "", "", "")
        for objective in collect_objs(dirs):
            keys = (
                objective["configuration"],
                objective["problem"],
                objective["model"],
                objective["data_file"],
            )
            writer.writerow(objective)
            if last_keys != keys:
                count += 1
                last_keys = keys

    click.echo(f"Processed objectives from {count} files.", err=True)


@main.command()
@click.argument("dirs", nargs=-1, type=click.Path(exists=True, dir_okay=True))
@click.argument("out_file", nargs=1, type=click.Path(file_okay=True))
def collect_statistics(dirs: Iterable[str], out_file: str):
    """Collects statistics values and combines them into a single CSV file.

    \b
    DIRS are directories containing the result YAML files
    OUT_FILE is the CSV file containing aggregated statistics data
    """

    statistics = list(collect_stats(dirs))
    keys = {key for obj in statistics for key in obj.keys()}
    keys = keys.difference(STANDARD_KEYS)
    with Path(out_file).open(mode="w") as file:
        writer = csv.DictWriter(
            file, STANDARD_KEYS + list(keys), dialect="unix", extrasaction="ignore"
        )
        writer.writeheader()
        for stat in statistics:
            writer.writerow(stat)
    click.echo(f"Processed statistics from {len(statistics)} files.", err=True)


@main.command()
@click.option(
    "-c",
    "--check",
    default=1,
    help="""Number of solutions to check per instance
            (randomly chooses which, but always checks final solution).
            Setting to zero will check all solutions.
            """,
)
@click.option(
    "-b",
    "--base-dir",
    default=".",
    help="Base directory for model/data file resolution",
    type=click.Path(exists=True, dir_okay=True),
)
@click.argument("dir", nargs=1, type=click.Path(exists=True, dir_okay=True))
@click.argument("pytest_args", nargs=-1)
def check_solutions(check: int, base_dir: str, dir: str, pytest_args: Iterable[str]):
    """Checks the correctness of solutions produced during a minizinc-slurm run.

    This is done by feeding the solution produced back into the model and checking
    that is is still satisfiable.

    \b
    DIR is the directory containing YAML output from minizinc-slurm
    PYTEST_ARGS are passed to the underlying PyTest command
    """
    try:
        import pytest

        args = [
            "-p",
            "mzn_bench.pytest.check_solutions",
            "--check",
            str(check),
            "--base-dir",
            base_dir,
            dir,
        ]
        args.extend(pytest_args)
        exit(pytest.main(args))
    except ImportError:
        click.echo(IMPORT_ERROR, err=True)
        exit(1)


@main.command()
@click.argument("dir", nargs=1, type=click.Path(exists=True, dir_okay=True))
@click.argument("pytest_args", nargs=-1)
def check_statuses(dir: str, pytest_args: Iterable[str]):
    """Checks for incorrect proof of optimality/unsatisfiability.

    This can only be run after the check-solutions command has been run.

    \b
    DIR is the directory containing YAML output from minizinc-slurm
    PYTEST_ARGS are passed to the underlying PyTest command
    """

    try:
        import pytest

        args = ["-p", "mzn_bench.pytest.check_statuses", dir]
        args.extend(pytest_args)
        exit(pytest.main(args))
    except ImportError:
        click.echo(IMPORT_ERROR, err=True)
        exit(1)


@main.command()
@click.option(
    "--per-problem",
    is_flag=True,
    help="Create a row for every problem",
)
@click.option(
    "--per-model",
    is_flag=True,
    help="Create a row for every model",
)
@click.option(
    "--per-instance",
    is_flag=True,
    help="Create a row for every instance / data-file",
)
@click.option(
    "--avg",
    type=click.Choice(["time", "solveTime", "flatTime"]),
    help="Show average of the given stat in the table",
)
@click.option(
    "--output-mode",
    type=click.Choice(tabulate_options, case_sensitive=False),
    default="pretty",
    help="The table format used in the output. All valid tablefmt values are allow, try `latex` for example.",
)
@click.argument(
    "statistics", metavar="stats_file", type=click.Path(exists=True, file_okay=True)
)
def report_status(
    per_problem: bool,
    per_model: bool,
    per_instance: bool,
    statistics: str,
    avg: str,
    output_mode: str,
):
    """Aggregate status of MiniZinc instance runs into a table

    STATS_FILE is the CSV file containing aggregated statistics data
    """
    try:
        from .analysis.report_status import report_status as report_status_fn

        print(
            report_status_fn(
                per_problem, per_model, per_instance, Path(statistics), avg, output_mode
            )
        )
    except ImportError:
        click.echo(IMPORT_ERROR, err=True)
        exit(1)


@main.command()
@click.argument(
    "statistics", metavar="stats_file", type=click.Path(exists=True, file_okay=True)
)
@click.argument(
    "from_conf",
    metavar="from_conf",
)
@click.argument(
    "to_conf",
    metavar="to_conf",
)
@click.option(
    "--time-delta",
    default=0.1,
    type=float,
    help="Fraction of time change considered to be significant",
)
@click.option(
    "--obj-delta",
    default=0.1,
    type=float,
    help="Fraction of objective value change considered to be significant",
)
@click.option(
    "--output-mode",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="The format used in the output.",
)
def compare_configurations(
    statistics: str,
    from_conf: str,
    to_conf: str,
    time_delta: float,
    obj_delta: float,
    output_mode: str,
):
    """Show all significant performance changes between two configurations"""
    try:
        from .analysis.analyse_changes import compare_configurations as fn

        result = fn(Path(statistics), from_conf, to_conf, time_delta, obj_delta)
        if output_mode != "human":
            result = result.serialise(output_mode)

        print(result)
    except ImportError:
        click.echo(IMPORT_ERROR, err=True)
        exit(1)


if __name__ == "__main__":
    main()
