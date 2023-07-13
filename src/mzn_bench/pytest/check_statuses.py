from typing import Any, Dict

import pytest
from minizinc import Method, Status
from pathlib import Path
from mzn_bench import yaml


class StatsFile(pytest.File):
    def collect(self):
        with self.fspath.open() as fp:
            stats = yaml.load(fp)
            name = ":".join(
                (
                    stats["configuration"],
                    stats["problem"],
                    stats["model"],
                    stats["data_file"],
                )
            )
            yield StatsItem.from_parent(self, name=name, stats=stats)


class StatsItem(pytest.Item):
    stats: Dict[str, Any]

    def __init__(self, stats: Dict[str, any], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = stats

    def runtest(self):
        status = Status[self.stats["status"]]
        key = "{}_{}_{}".format(
            self.stats["problem"], self.stats["model"], self.stats["data_file"]
        )
        if status is Status.ERROR:
            pytest.skip("skipping {} as status was ERROR".format(key))

        method = Method[self.stats["method"].upper()]
        if status is Status.UNSATISFIABLE:
            is_satisfiable = self.config.cache.get("sat/" + key, False)
            assert not is_satisfiable, "Incorrect UNSAT status"
        if status is Status.OPTIMAL_SOLUTION:
            min_obj, max_obj = self.config.cache.get("obj/" + key, (None, None))
            assert (
                method is Method.MAXIMIZE
                and (max_obj is None or self.stats["objective"] == max_obj)
            ) or (
                method is Method.MINIMIZE
                and (min_obj is None or self.stats["objective"] == min_obj)
            ), "Incorrect optimality proof"

    def reportinfo(self):
        return self.fspath, 0, "usecase: {}".format(self.name)


def pytest_collect_file(parent, path):
    if path.basename.endswith("_stats.yml"):
        return StatsFile.from_parent(parent, path=Path(path))
