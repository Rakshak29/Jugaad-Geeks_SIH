"""Domain exceptions.

Raised by the domain layer, mapped to HTTP centrally in `app/api/main.py`.
No route handler ever raises an HTTP exception directly — route handlers contain
zero business logic, and deciding that something is a 422 is business logic
(Piece 1 §3.16).
"""

from __future__ import annotations


class ECEError(Exception):
    """Base for everything this system raises deliberately."""


class NotFoundError(ECEError):
    def __init__(self, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} not found: {identifier}")


class NotInCoverageSetError(ECEError):
    """Simulating someone who is not available to begin with.

    A departed employee is mechanically identical to a permanent, already-applied
    unavailability, so there is nothing to simulate (Piece 3 §4.1, §10.1).
    """

    def __init__(self, employee_id: str, reason: str = "departed") -> None:
        self.employee_id = employee_id
        self.reason = reason
        super().__init__(
            f"{employee_id} is not in the coverage set ({reason}); "
            f"their unavailability is already applied."
        )


class NoFrozenTreeError(ECEError):
    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"Expected exactly one frozen capability tree, found {count}. "
            f"Run the pipeline: `ece pipeline run`."
        )


class MissingConfigError(ECEError):
    """A config key was read before it was written.

    Fails loudly on purpose.  Derived thresholds are computed once at dataset
    freeze; a missing one means calibration did not run, and silently defaulting
    would let the engine state conclusions from a value nobody chose.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"config key '{key}' is not set. Derived values are written at "
            f"dataset freeze — run `ece freeze` (or `ece dataset build`)."
        )


class InvalidEdgeError(ECEError):
    def __init__(self, message: str, from_component: str, to_component: str) -> None:
        self.from_component = from_component
        self.to_component = to_component
        super().__init__(message)


class InvariantViolation(ECEError):
    """A freeze-time invariant failed.  Names the node and the rule (Piece 2 §10)."""

    def __init__(self, invariant: str, detail: str) -> None:
        self.invariant = invariant
        self.detail = detail
        super().__init__(f"{invariant} violated: {detail}")


class IngestionError(ECEError):
    pass


class OptimizerError(ECEError):
    """The CP-SAT solve did not return a usable answer.

    Never silently papered over: the weight of the "provably minimal team"
    claim is exactly why a failed solve must fail loudly.
    """


class InvalidRequestError(ECEError):
    """A request the API contract explicitly forbids — conflicting or absent
    discriminators (e.g. /generate-coverage-team with both or neither of
    employee_id / capability_id), or asking for a grouping node as a
    capability (Piece 6 API-007)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NamerUnavailable(ECEError):
    """The configured namer cannot run.

    Never fatal: naming falls back to the deterministic rule namer and the run
    report flags it.  Nothing downstream of naming depends on the model, which
    is what keeps the LLM off the path from a click to an answer (SC9).
    """
