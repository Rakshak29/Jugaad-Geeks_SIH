"""Evidence bands.

Piece 0 §6 (SC3): band codes are ORDINAL, never cardinal.  The integers exist so
code can compare, sort, take a maximum and test against a threshold.  They must
never be summed or averaged — two MODERATE people are not one HIGH person, and a
person who is "2.5 covered" across four capabilities is a meaningless statement.

That commitment is enforced here mechanically rather than by discipline:
`Band` supports comparison and `max()`, and raises `TypeError` on `+`, `-`, `/`
and on participation in `sum()`.  The forbidden version of the optimizer's
fourth tier — `max Σ band_code(p,c)·y[p][c]` — therefore fails loudly in CI
instead of producing a plausible-looking number.
"""

from __future__ import annotations

from enum import IntEnum


class _NoArithmetic:
    """Mixin that makes a value comparable and orderable but not summable."""

    __slots__ = ()

    def _forbid(self, other: object) -> "TypeError":
        return TypeError(
            f"Band codes are ordinal and must never be summed or averaged "
            f"(Piece 0 §6, SC3). Attempted arithmetic on {self!r} and {other!r}. "
            f"Use max(), a comparison against coverage_threshold, or a COUNT of "
            f"assignments at a given band instead."
        )

    def __add__(self, other): raise self._forbid(other)
    def __radd__(self, other): raise self._forbid(other)
    def __sub__(self, other): raise self._forbid(other)
    def __rsub__(self, other): raise self._forbid(other)
    def __mul__(self, other): raise self._forbid(other)
    def __rmul__(self, other): raise self._forbid(other)
    def __truediv__(self, other): raise self._forbid(other)
    def __rtruediv__(self, other): raise self._forbid(other)
    def __floordiv__(self, other): raise self._forbid(other)


class Band(_NoArithmetic, IntEnum):
    """NONE < LOW < MODERATE < HIGH.

    Meaning (Piece 3 §7.1):
        HIGH      has operated this under real conditions — or built most of it
        MODERATE  has built or maintained it
        LOW       has been adjacent to it
        NONE      no qualifying evidence
    """

    NONE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return self.name

    @classmethod
    def from_code(cls, code: int) -> "Band":
        return cls(code)

    def __str__(self) -> str:          # so f-strings render "HIGH", not "Band.HIGH"
        return self.name


#: Ordered strongest-first, for deterministic reporting.
BANDS_DESC: tuple[Band, ...] = (Band.HIGH, Band.MODERATE, Band.LOW, Band.NONE)


def strongest(bands) -> Band:
    """The band a person holds = the highest ceiling any single work unit reached.

    Piece 3 §7 rule 1.  A max, never a sum — which is why this helper exists
    rather than letting call sites reach for `sum()` out of habit.
    """
    best = Band.NONE
    for b in bands:
        if b > best:
            best = b
    return best
