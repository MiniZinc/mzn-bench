import minizinc

from datetime import timedelta
from pathlib import Path

# Configure me
instances = Path("instances.csv")
solvers = [
   (minizinc.Solver.lookup("chuffed"), {}, None),
   (minizinc.Solver.lookup("gecode"), {}, None),
]
timeout = timedelta(minutes=15)
processes = None
random_seed = None
free_search = True
optimisation_level = None

