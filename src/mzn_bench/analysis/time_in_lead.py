"""Pairwise time-in-lead scoring.

Each run is a step function of its state over time, with one step per second up
to the time limit T. At the end of second t, the state of a run is:

- no solution yet: the worst state,
- the best objective found so far (larger is better after negating minimize
  objectives),
- the final objective plus 1/2 from the time optimality is proven onward,
- the best state from the time unsatisfiability is proven onward,
- 1 for a satisfaction instance, from the time it is solved onward.

The score of configuration A against configuration B on one instance is the
fraction of seconds 1..T in which A has the better state. Seconds in which the
states are equal (including both without a solution) give 1/2 to each. So the
two scores for a pair on one instance always sum to 1.

Times are quantized to whole seconds: an event at x seconds counts from second
max(1, floor(x)) onward.
"""

import math
from typing import Optional

import numpy as np
import pandas as pd
from minizinc.result import Status

NEG = -np.inf
INSTANCE_KEYS = ["problem", "model", "data_file"]

SOLVED = {Status.SATISFIED, Status.ALL_SOLUTIONS, Status.OPTIMAL_SOLUTION}
PROVED = {Status.OPTIMAL_SOLUTION, Status.ALL_SOLUTIONS}
INFEASIBLE = {Status.UNSATISFIABLE, Status.UNBOUNDED}


def qtime(seconds) -> np.ndarray:
    """Quantize times in seconds to whole seconds: max(1, floor(x))."""
    return np.maximum(1, np.floor(np.asarray(seconds, dtype=float))).astype(np.int64)


def infer_time_limit(stats: pd.DataFrame) -> int:
    """Infer the time limit (in whole seconds) from a statistics data frame.

    Runs that did not finish (status UNKNOWN, or SATISFIED on an optimization
    instance) ran until the time limit: the limit is the floor of their largest
    time. If every run finished, the limit is the ceiling of the largest time.
    """
    status = stats["status"].map(Status.from_str)
    opt = stats["method"].isin(["minimize", "maximize"])
    timed_out = (status == Status.UNKNOWN) | ((status == Status.SATISFIED) & opt)
    times = stats.loc[timed_out, "time"].dropna()
    if not times.empty:
        return max(1, math.floor(times.max()))
    times = stats.loc[status != Status.ERROR, "time"].dropna()
    if times.empty:
        raise ValueError("Cannot infer the time limit: no run has a time")
    return max(1, math.ceil(times.max()))


def run_state(
    method: str,
    status: Status,
    time: float,
    objective: Optional[float],
    trace_times: np.ndarray,
    trace_objs: np.ndarray,
    time_limit: int,
) -> np.ndarray:
    """State of one run at the end of each second t = 0..time_limit.

    Index 0 is unused and holds the worst state.
    """
    row = np.full(time_limit + 1, NEG)
    if status in (Status.ERROR, Status.UNKNOWN):
        return row
    end = time_limit if pd.isna(time) else int(qtime(time))
    if method == "satisfy":
        if status in SOLVED or status in INFEASIBLE:
            row[end:] = 1.0
        return row
    sign = -1.0 if method == "minimize" else 1.0
    if len(trace_times):
        order = np.argsort(trace_times, kind="stable")
        q = qtime(trace_times[order])
        vals = sign * trace_objs[order]
        grid = np.arange(1, time_limit + 1)
        idx = np.searchsorted(q, grid, side="right") - 1
        row[1:] = np.where(idx >= 0, vals[np.maximum(idx, 0)], NEG)
    if status in INFEASIBLE:
        row[end:] = np.inf
    elif status in PROVED:
        if objective is None or np.isnan(objective):
            objective = trace_objs[np.argmax(trace_times)] if len(trace_objs) else None
        if objective is not None:
            row[end:] = sign * objective + 0.5
    return row


def lead_fraction(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of seconds 1..T in which state row a leads state row b (ties 1/2)."""
    a, b = a[1:], b[1:]
    return float(np.mean((a > b) + 0.5 * (a == b)))


class TimeInLead:
    """State rows for every (configuration, instance) in a statistics data frame."""

    def __init__(self, stats: pd.DataFrame, objectives: pd.DataFrame, time_limit: int):
        self.time_limit = time_limit
        objs = objectives.copy()
        objs["data_file"] = objs["data_file"].fillna("")
        objs["model"] = objs["model"].fillna("")
        objs = objs.dropna(subset=["time", "objective"])
        self._traces = {
            key: (
                grp["time"].to_numpy(dtype=float),
                grp["objective"].to_numpy(dtype=float),
            )
            for key, grp in objs.groupby(["configuration"] + INSTANCE_KEYS)
        }
        self._states: dict = {}
        for instance, inst_df in stats.groupby(INSTANCE_KEYS):
            methods = inst_df["method"].dropna()
            method = methods.iloc[0] if not methods.empty else "satisfy"
            if method not in ["satisfy", "maximize", "minimize"]:
                raise ValueError(f"Unknown method '{method}' for instance {instance}")
            for _, run in inst_df.iterrows():
                key = (run["configuration"],) + tuple(instance)
                if key in self._states:
                    raise ValueError(
                        f"Configuration '{key[0]}' has more than one run on instance {instance}"
                    )
                times, vals = self._traces.get(key, (np.array([]), np.array([])))
                obj = run.get("objective", None)
                self._states[key] = run_state(
                    method,
                    Status.from_str(run["status"]),
                    run["time"],
                    None if pd.isna(obj) else float(obj),
                    times,
                    vals,
                    time_limit,
                )

    def score(self, df: pd.DataFrame, conf: str, other_conf: str) -> tuple:
        """Total time-in-lead of conf and other_conf over the instances in df.

        Instances on which either configuration has no run are skipped.
        """
        score = other_score = 0.0
        for instance in df[INSTANCE_KEYS].drop_duplicates().itertuples(index=False):
            a = self._states.get((conf,) + tuple(instance))
            b = self._states.get((other_conf,) + tuple(instance))
            if a is None or b is None:
                continue
            lead = lead_fraction(a, b)
            score += lead
            other_score += 1.0 - lead
        return score, other_score
