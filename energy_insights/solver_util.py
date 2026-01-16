"""
Utils for dealing with different LP solvers via PuLP.
"""

import os
import sys

from enum import Enum
from typing import Optional

from pulp import (
    CPLEX_PY,
    GUROBI_CMD,
    HiGHS_CMD,
    LpProblem,
    MOSEK,
    PULP_CBC_CMD,
    XPRESS_PY,
)

from .logging import get_logger

logger = get_logger(__name__)

# Import COPT solver library only if it is installed (i.e. if COPT_HOME is in env).
copt_pulp_path: Optional[str] = os.getenv("COPT_HOME")
if copt_pulp_path is not None:
    sys.path.append(os.path.join(copt_pulp_path, "lib", "pulp"))
    from copt_pulp import COPT_DLL


class Solver(Enum):
    CBC = "CBC"
    COPT = "COPT"
    CPLEX = "CPLEX"
    GUROBI = "Gurobi"
    HIGHS = "HiGHS"
    MOSEK = "Mosek"
    XPRESS = "Xpress"


def get_solver_by_name(name: str) -> Optional[Solver]:
    """Returns the Solver that has enum value corresponding to the provided `name`, or None if such
    solver does not exist."""
    try:
        return Solver(name)
    except ValueError:
        return None


def _solve(
    prob: LpProblem,
    solver: Solver,
    timeout_minutes: Optional[int] = None,
    shift_ipm_termination_by_orders: int = 0,
) -> bool:
    if solver == Solver.CBC and PULP_CBC_CMD().available():
        logger.debug("Using solver CBC")
        prob.solve(PULP_CBC_CMD())
    elif (
        solver == Solver.COPT and copt_pulp_path is not None and COPT_DLL().available()
    ):
        logger.debug("Using solver COPT")
        prob.solve(COPT_DLL())
    elif solver == Solver.CPLEX and CPLEX_PY().available():
        logger.debug("Using solver CPLEX")
        prob.solve(CPLEX_PY(mip=False))
    elif solver == Solver.GUROBI and GUROBI_CMD().available():
        logger.debug("Using solver Gurobi")
        prob.solve(GUROBI_CMD())
    elif solver == Solver.HIGHS and HiGHS_CMD().available():
        logger.debug("Using solver HiGHS")
        # Disable mixed-integer optimization and enable interior point
        # (IPM) solver for faster optimization.
        prob.solve(HiGHS_CMD(options=["--solver=ipm"]))
    elif solver == Solver.MOSEK and MOSEK().available():
        options = {
            # Generate a report and an irreducible infeasible system
            # (IIS) when the problem is infeasible.
            "MSK_IPAR_INFEAS_REPORT_AUTO": 1,
            "MSK_IPAR_LOG_INFEAS_ANA": 1,
            "MSK_IPAR_WRITE_IGNORE_INCOMPATIBLE_ITEMS": 1,
            # Select interior point solver (which should be enabled by default).
            "MSK_IPAR_OPTIMIZER": 4,
            # Wait for a license to become available if all are used.
            "MSK_IPAR_LICENSE_WAIT": 1,
        }
        if timeout_minutes:
            options["MSK_DPAR_OPTIMIZER_MAX_TIME"] = timeout_minutes * 60
        if shift_ipm_termination_by_orders > 0:
            shift_factor = 10**shift_ipm_termination_by_orders
            options["MSK_DPAR_INTPNT_TOL_PFEAS"] = 1.0e-8 / shift_factor
            options["MSK_DPAR_INTPNT_TOL_DFEAS"] = 1.0e-8 / shift_factor
            options["MSK_DPAR_INTPNT_TOL_REL_GAP"] = 1.0e-8 / shift_factor
            options["MSK_DPAR_INTPNT_TOL_INFEAS"] = 1.0e-10 / shift_factor
        logger.debug("Using solver Mosek")
        prob.solve(MOSEK(options=options))
    elif solver == Solver.XPRESS and XPRESS_PY().available():
        logger.debug("Using solver Xpress")
        # Disable mixed-integer optimization and enable interior point
        # (IPM) solver for faster optimization.
        prob.solve(XPRESS_PY(mip=False, options=["DEFAULTALG=4"]))
    else:
        return False
    return True


def solve_problem(
    prob: LpProblem,
    preferred_solver: Optional[Solver] = None,
    timeout_minutes: Optional[int] = None,
    shift_ipm_termination_by_orders: int = 0,
):
    """
    Solves the provided LpProblem `prob` using the `preferred_solver`. If `preferred_solver` is
    None, the function chooses the best available solver on its own.
    """
    if preferred_solver is not None:
        solved = _solve(
            prob, preferred_solver, timeout_minutes, shift_ipm_termination_by_orders
        )
        assert solved, f"selected solver {preferred_solver.value} is not available"
        return
    solved = (
        _solve(prob, Solver.MOSEK, timeout_minutes, shift_ipm_termination_by_orders)
        or _solve(prob, Solver.GUROBI, timeout_minutes, shift_ipm_termination_by_orders)
        or _solve(prob, Solver.XPRESS, timeout_minutes, shift_ipm_termination_by_orders)
        or _solve(prob, Solver.CPLEX, timeout_minutes, shift_ipm_termination_by_orders)
        or _solve(prob, Solver.COPT, timeout_minutes, shift_ipm_termination_by_orders)
        or _solve(prob, Solver.HIGHS, timeout_minutes, shift_ipm_termination_by_orders)
        or _solve(prob, Solver.CBC, timeout_minutes, shift_ipm_termination_by_orders)
    )
    assert solved, "no solver is available"
