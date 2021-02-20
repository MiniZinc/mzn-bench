import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import ruamel.yaml


def collect_instances(benchmarks_location: str):
    for root, _, files in os.walk(benchmarks_location):
        for name in files:
            if name.endswith(".mzn"):
                problem = root.split(os.sep)[-1]
                datafiles = 0
                for nroot, _, nfiles in os.walk(root):
                    for nname in nfiles:
                        if nname.endswith(".dzn") or nname.endswith(".json"):
                            datafiles += 1
                            yield {
                                "problem": problem,
                                "model": Path(root).absolute() / name,
                                "data_file": Path(nroot).absolute() / nname,
                            }

                if datafiles == 0:
                    yield {
                        "problem": problem,
                        "model": Path(root).absolute() / name,
                        "data_file": None,
                    }


def collect_objectives(dirs: Iterable[Union[str, Path]]) -> List[Dict[str, Any]]:
    base_keys = ["configuration", "problem", "model", "data_file", "time"]
    for dir in dirs:
        path = (dir if isinstance(dir, Path) else Path(dir)).resolve()
        for file in path.rglob("*_sol.yml"):
            with file.open() as fp:
                sols = ruamel.yaml.safe_load(fp)
                for sol in sols or []:
                    if "solution" not in sol:
                        continue
                    obj = sol["solution"].get("objective", None)
                    item = {k: sol[k] for k in base_keys}
                    item["objective"] = obj
                    item["run"] = path.name
                    yield item


def collect_statistics(
    dirs: Iterable[Union[str, Path]], filter_stats: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    base_keys = ["configuration", "problem", "model", "data_file", "time"]
    for dir in dirs:
        path = (dir if isinstance(dir, Path) else Path(dir)).resolve()
        for file in path.rglob("*_stats.yml"):
            with file.open() as fp:
                stats = ruamel.yaml.safe_load(fp)
                if filter_stats is not None:
                    stats = {k: stats[k] for k in base_keys + filter_stats}
                stats["run"] = path.name
                yield stats


def read_csv(sols: str, stats: str):
    import pandas as pd

    sols_df = pd.read_csv(sols)
    stats_df = pd.read_csv(stats)
    sols_df.data_file = sols_df.data_file.fillna("")
    stats_df.data_file = stats_df.data_file.fillna("")
    return sols_df, stats_df
