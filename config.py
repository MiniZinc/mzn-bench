import minizinc
from datetime import timedelta
from pathlib import Path

# Configure me
instances = Path("instances.csv")
solvers = [
    minizinc.Solver.lookup("chuffed"),
    minizinc.Solver.lookup("gecode"),
]
timeout = timedelta(minutes=1)
processes = None
random_seed = None
free_search = True
optimisation_level = None

