#!/usr/bin/env python3
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Dict, List

# The difference in objectives for them to be considered the same
SAME_DELTA = 1e-6
# Status changes (from, to) considered positive
POSITIVE_STATUS_CHANGES = [
    ("ERROR", "SATISFIED"),
    ("ERROR", "UNSATISFIABLE"),
    ("ERROR", "OPTIMAL_SOLUTION"),
    ("ERROR", "UNKNOWN"),
    ("UNKNOWN", "SATISFIED"),
    ("UNKNOWN", "UNSATISFIABLE"),
    ("UNKNOWN", "OPTIMAL_SOLUTION"),
    ("SATISFIED", "OPTIMAL_SOLUTION"),
]
# Status changes (from, to) considered a conflict
CONFLICT_STATUS_CHANGES = [
    ("UNSATISFIABLE", "SATISFIED"),
    ("SATISFIED", "UNSATISFIABLE"),
    ("UNSATISFIABLE", "OPTIMAL_SOLUTION"),
    ("OPTIMAL_SOLUTION", "UNSATISFIABLE"),
]


@dataclass
class PerformanceChanges:
    time_delta: float
    obj_delta: float
    # (from_status, to_status) -> (model, datafile)
    status_changes: Dict[Tuple[str, str], List[Tuple[str, str]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # model, datafile, from_time, to_time
    time_changes: List[Tuple[str, str, float, float]] = field(default_factory=list)
    # model, datafile, from_obj, to_obj, maximise?
    obj_changes: List[Tuple[str, str, float, float, bool]] = field(default_factory=list)
    # model, datafile, from_obj, to_obj
    obj_conflicts: List[Tuple[str, str, float, float]] = field(default_factory=list)
    # model, datafile
    missing_instances: List[Tuple[str, str]] = field(default_factory=list)

    def __str__(self):
        obj_sort_key = lambda it: (1 if it[4] else -1) * (it[3] - it[2]) / it[2]

        n_status_changes = sum([len(li) for key, li in self.status_changes.items()])
        n_pos_status_changes = 0
        n_bad_status_changes = 0

        stat_bad_str = ""
        stat_pos_str = ""
        stat_neg_str = ""

        for change, li in self.status_changes.items():
            s = f"{change[0]} -> {change[1]}:\n"
            for i in li:
                s += f"  - {i[0]} {i[1]}\n"
            if change in CONFLICT_STATUS_CHANGES:
                n_bad_status_changes += len(li)
                stat_bad_str += s
            elif change in POSITIVE_STATUS_CHANGES:
                n_pos_status_changes += len(li)
                stat_pos_str += s
            else:
                stat_neg_str += s

        if stat_bad_str != "":
            stat_bad_str = (
                "Conflicting Status Changes:\n---------------------------\n"
                + stat_bad_str
            )
        if stat_pos_str != "":
            stat_pos_str = (
                "Positive Status Changes:\n------------------------\n" + stat_pos_str
            )
        if stat_neg_str != "":
            stat_neg_str = (
                "Negative Status Changes:\n------------------------\n" + stat_neg_str
            )

        output = f"Summary:\n" f"========\n"
        if len(self.missing_instances) > 0:
            output += f"- Missing instances: {len(self.missing_instances)}\n"
        if len(self.obj_conflicts) > 0:
            output += f"- Objective conflicts: {len(self.obj_conflicts)}\n"
        output += (
            f"- Status Changes: {n_status_changes} ({'conflicts: ' + str(n_bad_status_changes) + ', ' if n_bad_status_changes > 0 else ''}positive: {n_pos_status_changes})\n"
            f"- Runtime Changes: {len(self.time_changes)} (positive: {len([x for x in self.time_changes if (x[3] - x[2]) / x[2] < 0])})\n"
            f"- Objective Changes: {len(self.obj_changes)} (positive: {len([x for x in self.obj_changes if obj_sort_key(x) > 0])})\n"
        )
        output += "\n\n"

        if len(self.missing_instances) > 0:
            output += "Missing Instances:\n==================\n"
            for it in self.missing_instances:
                output += f"- {it[0]} {it[1]}"
            output += "\n"
        if len(self.obj_conflicts) > 0:
            output += (
                f"Objective Conflicts (±{SAME_DELTA}):\n=============================\n"
            )
            for it in self.obj_conflicts:
                output += f"- ({it[2]} != {it[3]}) {it[0]} {it[1]}\n"
            output += "\n"

        output += (
            f"Status Changes:\n===============\n{stat_bad_str}\n{stat_neg_str}\n{stat_pos_str}\n"
            if n_status_changes > 0
            else ""
        )

        if len(self.time_changes) > 0:
            output += f"Timing Changes (>±{self.time_delta * 100:.1f}%):\n=========================\n"
            time_li = sorted(
                self.time_changes, key=lambda it: (it[3] - it[2]) / it[2], reverse=True
            )
            line = (time_li[0][3] - time_li[0][2]) / time_li[0][2] < 0
            for it in time_li:
                if not line and (it[3] - it[2]) / it[2] < 0:
                    output += "-------------------------\n"
                    line = True
                output += f"- ({(it[3] - it[2]) / it[2] * 100:.1f}%: {it[2]:.1f}s -> {it[3]:.1f}s) {it[0]} {it[1]}\n"
            output += "\n"

        if len(self.obj_changes) > 0:
            output += f"Objective Changes (>±{self.obj_delta * 100:.1f}%):\n============================\n"
            obj_li = sorted(
                self.obj_changes,
                key=obj_sort_key,
            )
            line = obj_sort_key(obj_li[0]) > 0
            for it in obj_li:
                if not line and obj_sort_key(it) > 0:
                    output += "----------------------------\n"
                    line = True
                output += f"- ({(it[3] - it[2]) / it[2] * 100:.1f}%: {'MAX' if it[4] else 'MIN'} {it[2]:.2f} -> {it[3]:.2f}) {it[0]} {it[1]}\n"
            output += "\n"

        return output.strip()

    def serialise(self, method: str) -> str:
        as_dict = {
            "status_changes": [
                {
                    "model": model,
                    "data": data,
                    "status_before": from_stat,
                    "status_after": to_stat,
                }
                for (from_stat, to_stat), li in self.status_changes.items()
                for model, data in li
            ],
            "time_delta": self.time_delta,
            "time_changes": [
                {
                    "model": model,
                    "data": data,
                    "time_before": from_time,
                    "time_after": to_time,
                }
                for (model, data, from_time, to_time) in self.time_changes
            ],
            "obj_delta": self.obj_delta,
            "obj_changes": [
                {
                    "model": model,
                    "data": data,
                    "obj_before": from_obj,
                    "obj_after": to_obj,
                    "maximise": is_max,
                }
                for (model, data, from_obj, to_obj, is_max) in self.obj_changes
            ],
            "obj_conflicts": [
                {
                    "model": model,
                    "data": data,
                    "obj_before": from_obj,
                    "obj_after": to_obj,
                }
                for (model, data, from_obj, to_obj) in self.obj_conflicts
            ],
            "missing_instances": [
                {
                    "model": model,
                    "data": data,
                }
                for (model, data) in self.missing_instances
            ],
        }

        assert method == "json"
        return json.dumps(as_dict)

def read_row(row: dict):
    return (
        row["status"],
        float(math.nan if row["time"] == "" else row["time"]),
        float(row["objective"] if "objective" in row and row["objective"] != "" else math.nan),
        row["method"],
    )

def compare_configurations(
    statistics: Path, from_conf: str, to_conf: str, time_delta: float, obj_delta: float
) -> PerformanceChanges:
    from_stats = {}
    to_stats = {}

    with statistics.open() as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            key = (row["model"], row["data_file"])
            if row["configuration"] == from_conf:
                from_stats[key] = read_row(row)
            elif row["configuration"] == to_conf:
                to_stats[key] = read_row(row)

    changes = PerformanceChanges(time_delta, obj_delta)

    for key, from_val in from_stats.items():
        to_val = to_stats.get(key, None)
        if to_val is None:
            changes.missing_instances.append(key)
        elif from_val[0] != to_val[0]:
            changes.status_changes[(from_val[0], to_val[0])].append(key)
        elif from_val[0] == "OPTIMAL_SOLUTION" or (
            from_val[0] == "SATISFIED" and from_val[3] == "satisfy"
        ):
            time_div = from_val[1] if from_val[1] != 0.0 else 0.1
            time_change = (to_val[1] - from_val[1]) / time_div
            if (
                from_val[0] == "OPTIMAL_SOLUTION"
                and abs(from_val[2] - to_val[2]) > SAME_DELTA
            ):
                changes.obj_conflicts.append((key[0], key[1], from_val[2], to_val[2]))
            elif abs(time_change) > time_delta:
                changes.time_changes.append((key[0], key[1], from_val[1], to_val[1]))
        elif from_val[0] == "SATISFIED" and from_val[3] != "satisfy":
            obj_div = from_val[2] if from_val[2] != 0.0 else 0.1
            obj_change = (to_val[2] - from_val[2]) / obj_div
            if abs(obj_change) > obj_delta:
                changes.obj_changes.append(
                    (key[0], key[1], from_val[2], to_val[2], from_val[3] == "maximize")
                )

    return changes
