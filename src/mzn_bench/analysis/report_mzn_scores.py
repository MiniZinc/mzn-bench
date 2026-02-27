import itertools
from pathlib import Path

import pandas as pd
from minizinc.result import Status
from tabulate import tabulate


def calculate_mzn_scores(
    df: pd.DataFrame,
    conf: str,
    other_conf: str,
    time_limit: int = 1200,
    complete: bool = True,
) -> dict:
    """
    Compute MiniZinc challenge scores using the complete scoring method.
    For more information, see:
    Peter J. Stuckey, R. Becket, J. Fischer (2010). Philosophy of the MiniZinc challenge. Constraints 15 (3), 307-316.
    params: df: DataFrame containing the results of the MiniZinc challenge
    params: conf: List of configurations to compare
    params: other_conf: Baseline configuration to compare against
    params: time_limit: Time limit for the solver
    params: complete: Whether to use complete scoring or not
    return: Dictionary with the scores for each configuration
    """
    mzn_scores = {conf: 0.0, other_conf: 0.0}
    for instance, instance_df in df.groupby(["model", "data_file"]):
        # Skip if all configurations have the status "UNKNOWN"
        if instance_df["status"].map(Status.from_str).eq(Status.UNKNOWN).all():
            print(
                f"Skipping instance {instance} since all configurations have status UNKNOWN. "
            )
            continue

        # Determine the problem type based on the first non-NaN "method" attribute
        method_value = instance_df["method"].dropna()
        if method_value.empty:
            print(
                f"Skipping instance {instance} since all configurations have 'method' is N/A."
            )
            continue
        method = method_value.iloc[0]
        if method not in ["satisfy", "maximize", "minimize"]:
            raise ValueError(f"Unknown method '{method}' for instance {instance}")

        is_satisfaction = method == "satisfy"
        is_maximization = method == "maximize"
        is_minimization = method == "minimize"

        solver_df = instance_df[instance_df["configuration"] == conf]
        other_df = instance_df[instance_df["configuration"] == other_conf]

        # Skip if either configuration is not present in the instance
        if solver_df.empty or other_df.empty:
            continue

        # Get the status for each configuration
        status = Status.from_str(solver_df["status"].iloc[0])
        other_status = Status.from_str(other_df["status"].iloc[0])

        # Get the average time used for each configuration
        assert len(solver_df["time"]) == 1
        assert len(other_df["time"]) == 1
        time_used = min(solver_df["time"].mean(), time_limit)
        other_time_used = min(other_df["time"].mean(), time_limit)

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
        other_quality = other_df["objective"].iloc[0] if not is_satisfaction else None

        # If the other configuration is solved and the current one is not
        # give a score to the other configuration
        if other_solved and not solved:
            mzn_scores[other_conf] += 1
            continue

        # If the current configuration is solved and the other one is not
        # give a score to the current configuration
        if solved and not other_solved:
            mzn_scores[conf] += 1
            continue

        # If it is a satisfaction problem, compare the time used
        if is_satisfaction:
            mzn_scores[conf] += other_time_used / (time_used + other_time_used)
            mzn_scores[other_conf] += time_used / (time_used + other_time_used)
            continue

        # If it is complete scoring, compare whether the solution is optimal
        if complete and optimal and not other_optimal:
            mzn_scores[conf] += 1
            continue
        elif complete and other_optimal and not optimal:
            mzn_scores[other_conf] += 1
            continue

        # Compare the quality of the solutions
        if is_maximization:
            if quality > other_quality:
                mzn_scores[conf] += 1
                continue
            elif other_quality > quality:
                mzn_scores[other_conf] += 1
                continue
        elif is_minimization:
            if quality < other_quality:
                mzn_scores[conf] += 1
                continue
            elif other_quality < quality:
                mzn_scores[other_conf] += 1
                continue

        # If the qualities are equal, compare the time used
        mzn_scores[conf] += other_time_used / (time_used + other_time_used)
        mzn_scores[other_conf] += time_used / (time_used + other_time_used)

    return mzn_scores[conf], mzn_scores[other_conf]


def report_mzn_scores(
    grouping: str,
    statistics: Path,
    tablefmt: str,
    baseline: str | None = None,
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

    # If a baseline is provided, remove it from the list of configurations
    if baseline:
        configurations.remove(baseline)

    output = {conf: [] for conf in configurations}
    headers = ["configuration"]

    dataframes = {}
    if grouping == "all":
        # If grouping is "all", create a single group with all data
        dataframes["all"] = df
    else:
        # Otherwise, group by the specified column
        assert grouping in df.columns, (
            f"Grouping '{grouping}' not found in DataFrame columns"
        )
        for group_value in df[grouping].unique():
            group_df = df[df[grouping] == group_value]
            dataframes[group_value] = group_df

    # Iterate over the groups and calculate scores
    for group_value, sub_df in dataframes.items():
        if baseline:
            # Calculate scores for all configurations against the baseline
            for conf in configurations:
                conf_score, baseline_score = calculate_mzn_scores(
                    sub_df,
                    conf,
                    baseline,
                    time_limit,
                    complete,
                )
                output[conf].append("%.2f (%.2f)" % (conf_score, baseline_score))
        else:
            mzn_scores = {conf: 0.0 for conf in configurations}
            # Calculate scores for all configurations
            for conf, other_conf in itertools.combinations(configurations, 2):
                conf_score, other_conf_score = calculate_mzn_scores(
                    sub_df,
                    conf,
                    other_conf,
                    time_limit,
                    complete,
                )
                # Update the scores for each configuration
                mzn_scores[conf] += conf_score
                mzn_scores[other_conf] += other_conf_score

            # Append the scores to the output
            for conf in configurations:
                output[conf].append("%.2f" % mzn_scores[conf])

        headers.append(group_value)

    # Convert to list of lists for tabulate
    output = [[conf] + scores for conf, scores in output.items()]

    # Return the scores as a formatted table string
    return tabulate(
        output,
        headers=headers,
        tablefmt=tablefmt,
    )
