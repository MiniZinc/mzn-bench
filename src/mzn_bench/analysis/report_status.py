import csv
from pathlib import Path

from typing import Iterable, Optional
from tabulate import tabulate
from minizinc.result import Status


# TODO: Maybe this should be included in MiniZinc Python
def status_from_str(s: str) -> Status:
    for k, v in Status.__members__.items():
        if k == s.upper():
            return v


def report_status(
    keys: Iterable[str], statistics: Path, avg: str, tablefmt: str
):
    seen_status = set()
    table = {}
    with statistics.open() as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            key = [ row[key] for key in keys ]

            status = status_from_str(row["status"])
            seen_status.add(status)

            key = tuple(key)
            if key not in table:
                table[key] = dict()

            avg_value = row.get(avg, 0)
            time = float(0 if avg_value == "" else avg_value)
            if avg and status in [Status.OPTIMAL_SOLUTION, Status.UNSATISFIABLE]:
                if status not in table[key]:
                    table[key][status] = [time]
                else:
                    table[key][status].append(time)
            elif status == Status.SATISFIED:
                if avg:
                    entry = table[key].get(status, (0, []))
                    if row["method"] == "satisfy":
                        entry[1].append(time)
                    table[key][status] = (entry[0] + 1, entry[1])
                else:
                    entry = table[key].get(status, (0, 0))
                    table[key][status] = (
                        entry[0] + 1,
                        entry[1] + int(row["method"] == "satisfy"),
                    )
            else:
                entry = table[key].get(status, 0)
                table[key][status] = entry + 1

    status_order = [
        Status.OPTIMAL_SOLUTION,
        Status.UNSATISFIABLE,
        Status.SATISFIED,
        Status.UNKNOWN,
        Status.UNBOUNDED,
        Status.ERROR,
    ]

    output = []
    for key in sorted(table):
        row = table[key]
        line = list(key)
        for s in status_order:
            if s in seen_status:
                if s not in row:
                    o = 0
                elif avg and s in [
                    Status.OPTIMAL_SOLUTION,
                    Status.UNSATISFIABLE,
                ]:
                    o = f"{len(row[s])} ({sum(row[s]) / len(row[s]) :.2f}s)"
                elif s == Status.SATISFIED:
                    if avg:
                        o = f"{row[s][0]-len(row[s][1])} + {len(row[s][1])}"
                        if len(row[s][1]) > 0:
                            o += f" ({sum(row[s][1]) / len(row[s][1]) :.2f}s)"
                    else:
                        o = f"{row[s][0]-row[s][1]} + {row[s][1]}"
                else:
                    o = row[s]
                line.append(o)

        output.append(line)

    return tabulate(
        output,
        headers=(keys + [s for s in status_order if s in seen_status]),
        tablefmt=tablefmt,
    )
