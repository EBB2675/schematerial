"""Convenience aliases over real semantic-type CURIEs. Decision 4.

`semantic_type` has range `uriorcurie` and is open. Its value space is QUDT,
EMMO and PMDco, not a local enum, so what lives here is a set of aliases -- a
shorter way to write a CURIE that already exists, never a vocabulary of its own.
Any CURIE outside this table is just as valid and is carried verbatim.

Every alias below was resolved against the live vocabulary. An alias exists only
when the term

1. resolves,
2. means exactly what the alias name says, and
3. has a stable, readable CURIE.

The prototype's sixteen enum members are the input to that rule. Ten of them
pass and are here; the six that do not are recorded in
`docs/decisions/002-annotations-ontology-terms-and-semantic-types.md` with the
reason, because dropping them silently would look like an oversight.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

__all__ = [
    "ATOMIC_POSITION",
    "BAND_GAP",
    "CHARGE",
    "ENERGY",
    "FORCE",
    "LENGTH",
    "PRESSURE",
    "SEMANTIC_TYPE_ALIASES",
    "SPIN",
    "STRESS",
    "TEMPERATURE",
    "resolve_alias",
]

# http://qudt.org/vocab/quantitykind/, confirmed to resolve at the time of
# writing. Decision 4 names QUDT, EMMO and PMDco as the value space; only QUDT
# is drawn on here, because EMMO 1.0.3 gives these concepts opaque UUID CURIEs
# (WaveVector is emmo:EMMO_6074aa9d_7c3b_4011_b45a_4e7cde6f5f39) and nothing
# pins the EMMO version yet.
ENERGY: Final = "quantitykind:Energy"
LENGTH: Final = "quantitykind:Length"
FORCE: Final = "quantitykind:Force"
STRESS: Final = "quantitykind:Stress"
CHARGE: Final = "quantitykind:ElectricCharge"
SPIN: Final = "quantitykind:Spin"
TEMPERATURE: Final = "quantitykind:ThermodynamicTemperature"
PRESSURE: Final = "quantitykind:Pressure"
BAND_GAP: Final = "quantitykind:GapEnergy"
ATOMIC_POSITION: Final = "quantitykind:PositionVector"

SEMANTIC_TYPE_ALIASES: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "energy": ENERGY,
        "length": LENGTH,
        "force": FORCE,
        "stress": STRESS,
        "charge": CHARGE,
        "spin": SPIN,
        "temperature": TEMPERATURE,
        "pressure": PRESSURE,
        "band_gap": BAND_GAP,
        "atomic_position": ATOMIC_POSITION,
    }
)


def resolve_alias(value: str | None) -> str | None:
    """Expand a convenience alias, or return a CURIE unchanged.

    An unrecognised value is a CURIE this table does not happen to abbreviate,
    not an error and not `unknown`. It is returned verbatim, because decision 4
    puts the value space in the vocabularies rather than in this module.
    """
    if value is None:
        return None
    return SEMANTIC_TYPE_ALIASES.get(value, value)
