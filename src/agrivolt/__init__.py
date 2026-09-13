"""Agrivoltaic modelling for Indian conditions.

The package is a pipeline of small, independently testable stages:

    site + array geometry
        -> shading   (how much light reaches the canopy)
        -> pv        (how much electricity the array makes)
        -> water     (reference and shaded evapotranspiration)
        -> crop      (yield response to light and water)
        -> economics (two revenue streams, one balance sheet)

`scenario.run` composes them. Nothing below `scenario` imports anything above
it, so each stage can be exercised on its own.
"""

__version__ = "0.1.0"
