from pathlib import Path
import pandas as pd
import itertools

from typing import Iterable
from tabulate import tabulate
from minizinc.result import Status


def calculate_mzn_scores(
    df: pd.DataFrame,
    configurations: Iterable[str],
    time_limit: int,
    complete: bool,
) -> dict:
    """
    Compute MiniZinc challenge scores using the complete scoring method.
    For more information, see:
    Peter J. Stuckey, R. Becket, J. Fischer (2010). Philosophy of the MiniZinc challenge. Constraints 15 (3), 307-316.
    params: df: DataFrame containing the results of the MiniZinc challenge
    params: configurations: List of configurations to compare
    params: time_limit: Time limit for the solver
    params: complete: Whether to use complete scoring
    return: Dictionary with the scores for each configuration
    """
    mzn_scores = {config: 0 for config in configurations}
    for instance, instance_df in df.groupby(["model", "data_file"]):
        # Skip if all configurations have the status "UNKNOWN"
        if instance_df["status"].map(Status.from_str).eq(Status.UNKNOWN).all():
            print(
                f"Skipping instance {instance} since all configurations have status UNKNOWN. "
            )
            continue

        # Determine the problem type based on the first non-NaN "method" attribute
        method = instance_df["method"].dropna().iloc[0]
        is_satisfaction = method == "satisfy"
        is_maximization = method == "maximize"
        is_minimization = method == "minimize"

        for conf, other_conf in itertools.combinations(configurations, 2):
            solver_df = instance_df[instance_df["configuration"] == conf]
            other_df = instance_df[instance_df["configuration"] == other_conf]

            if solver_df.empty or other_df.empty:
                continue

            # Get the time used for each configuration
            time_used = min(solver_df["time"].iloc[0], time_limit)
            other_time_used = min(other_df["time"].iloc[0], time_limit)

            # Get the status for each configuration
            status = Status.from_str(solver_df["status"].iloc[0])
            other_status = Status.from_str(other_df["status"].iloc[0])

            # Check if the instance is solved by each configuration
            solved = status in [
                Status.SATISFIED,
                Status.UNSATISFIABLE,
                Status.OPTIMAL_SOLUTION,
            ]
            other_solved = other_status in [
                Status.SATISFIED,
                Status.UNSATISFIABLE,
                Status.OPTIMAL_SOLUTION,
            ]

            # Check if the instance is solved to optimal by each configuration
            if is_satisfaction:
                optimal = False
                other_optimal = False
            else:
                optimal = status in [Status.OPTIMAL_SOLUTION, Status.UNSATISFIABLE]
                other_optimal = other_status in [
                    Status.OPTIMAL_SOLUTION,
                    Status.UNSATISFIABLE,
                ]

            # Get the quality for each configuration
            quality = solver_df["objective"].iloc[0] if not is_satisfaction else None
            other_quality = (
                other_df["objective"].iloc[0] if not is_satisfaction else None
            )

            # Complete scoring
            if is_satisfaction:
                if other_solved and not solved:
                    mzn_scores[other_conf] += 1
                elif solved and not other_solved:
                    mzn_scores[conf] += 1
                else:
                    mzn_scores[conf] += other_time_used / (time_used + other_time_used)
                    mzn_scores[other_conf] += time_used / (time_used + other_time_used)
            elif is_maximization:
                if not solved and other_solved:
                    mzn_scores[other_conf] += 1
                elif solved and not other_solved:
                    mzn_scores[conf] += 1
                elif complete and optimal and not other_optimal:
                    mzn_scores[conf] += 1
                elif complete and other_optimal and not optimal:
                    mzn_scores[other_conf] += 1
                elif quality > other_quality:
                    mzn_scores[conf] += 1
                elif other_quality > quality:
                    mzn_scores[other_conf] += 1
                else:
                    mzn_scores[conf] += other_time_used / (time_used + other_time_used)
                    mzn_scores[other_conf] += time_used / (time_used + other_time_used)
            elif is_minimization:
                if not solved and other_solved:
                    mzn_scores[other_conf] += 1
                elif solved and not other_solved:
                    mzn_scores[conf] += 1
                elif complete and optimal and not other_optimal:
                    mzn_scores[conf] += 1
                elif complete and other_optimal and not optimal:
                    mzn_scores[other_conf] += 1
                elif quality < other_quality:
                    mzn_scores[conf] += 1
                elif other_quality < quality:
                    mzn_scores[other_conf] += 1
                else:
                    mzn_scores[conf] += other_time_used / (time_used + other_time_used)
                    mzn_scores[other_conf] += time_used / (time_used + other_time_used)
            else:
                raise ValueError(f"Unknown method '{method}' for instance {instance}")
    return mzn_scores


def report_mzn_scores(
    grouping: str,
    statistics: Path,
    tablefmt: str,
    time_limit: int = 1200,
    complete: bool = True,
) -> str:
    # Read the statistics file
    df = pd.read_csv(statistics)

    # Replace NaN values in "model" and "data_file" columns with empty strings
    df["model"] = df["model"].fillna("")
    df["data_file"] = df["data_file"].fillna("")

    # Get the list of configurations
    configurations = sorted(df["configuration"].unique())

    output = {conf: [] for conf in configurations}
    headers = ["configuration"]
    if grouping == "all":
        # Calculate scores for all configurations
        mzn_scores = calculate_mzn_scores(
            df,
            configurations,
            time_limit,
            complete,
        )

        # Normalize the scores with two digits after the decimal point
        for conf in configurations:
            output[conf].append("%.2f" % mzn_scores[conf])

        headers.append("scores")
    else:
        assert (
            grouping in df.columns
        ), f"Column '{grouping}' not found in the statistics file."
        # Get the list of groups (problem, model, or data_file)
        # and filter the dataframe based on the group
        groups = df[grouping].unique()
        for group_value in groups:
            # Filter the dataframe based on the group value
            group_df = df[df[grouping] == group_value]

            group_scores = calculate_mzn_scores(
                group_df,
                configurations,
                time_limit,
                complete,
            )

            # Normalize the scores with two digits after the decimal point
            for conf in configurations:
                output[conf].append("%.2f" % group_scores[conf])

            headers.append(group_value)

    # Convert to list of lists for tabulate
    output = [[conf] + scores for conf, scores in output.items()]
    # Return the scores as a formatted table string
    return tabulate(
        output,
        headers=headers,
        tablefmt=tablefmt,
    )
