import minizinc

from datetime import timedelta
from pathlib import Path

# Configure me
instances = Path("./instances.csv")
runs = [
  {"solver": minizinc.Solver.lookup("chuffed")},
  {"solver": minizinc.Solver.lookup("gecode")},
]
timeout = timedelta(minutes=15)
processes = None
random_seed = None
free_search = True
optimisation_level = None

