# agrivolt-model

Agrivoltaic yield, generation and revenue modelling for Maharashtra.

Solar arrays mounted above working farmland produce electricity and a crop from
the same hectare. Whether that is worth doing depends on a light budget, a water
balance and a tariff, and the answer is different in Solapur than it is in
Bavaria. This models it for Indian sites, from public data, reproducibly.

---

## The finding

Across four Maharashtra sites spanning the state's agro-climatic range, an
agrivoltaic array on a 15-acre parcel produces a **land equivalent ratio of 1.46
to 1.75** — the land does the work of about one and a half hectares per hectare.
That part matches the international literature.

The part that does not:

> **Every site needs ₹3.31–3.60/kWh to clear an 11% hurdle rate.
> MSKVY 2.0 pays ₹2.825/kWh.**

That is a gap of 49 to 78 paise, and it is remarkably stable across sites,
crops, and the full range of capex the market plausibly offers. No combination
of a realistic 2026 capex (₹38–52/Wp) and any tariff MERC discovered across the
257 MSKVY 2.0 substations clears the hurdle.

So the interesting question is not whether agrivoltaics works agronomically in
Maharashtra — the model says it does. It is that the state's flagship
decentralised solar scheme is priced for conventional ground mount, and the
structural premium for growing food underneath is currently unfunded. That is a
policy gap with a number attached to it.

| Site | Agro-climatic zone | LER | kWh/kWp | Crop margin ₹/yr | Breakeven ₹/kWh |
|---|---|---:|---:|---:|---:|
| Roha, Raigad | Konkan coastal, 2500 mm | 1.46 | 1713 | +54,486 | 3.588 |
| Solapur | Scarcity zone, semi-arid | 1.60 | 1810 | −176,219 | 3.464 |
| Nashik | Assured rainfall, horticultural | 1.75 | 1735 | +694,942 | 3.314 |
| Yavatmal | Vidarbha dryland | 1.47 | 1704 | −100,294 | 3.604 |

Five weather years each, 2019–2023. Reproduce with `agrivolt run`.

---

## Why India is not Bavaria

The agrivoltaics literature is overwhelmingly German, French and American, and
it carries an assumption from those climates: shade costs yield, and you accept
the cost because the electricity is worth more. Under a European light budget
that is correct.

Under a Maharashtra light budget it can invert, through two channels the
temperate literature has little reason to model:

**Water.** Shading cuts evapotranspiration. In a rainfed or deficit-irrigated
system that closes part of the water gap. At Roha, a rabi cowpea under the array
sees relative transpiration rise from 0.65 to 0.97, and **out-yields the same
crop in the open field — 0.73 t/ha against 0.54 t/ha, a 33% uplift** — despite
receiving 31% less light. Less light, more food. The model produces that from a
FAO-56 water balance, not from an assumption.

Note that this is the crop compared against itself grown in the open. The
separate Konkan point below — that the land grows nothing at all in rabi today —
is a different and larger claim, and the two are kept apart deliberately.

**Heat.** Yield across Marathwada and Vidarbha is frequently set by a handful of
days when the canopy exceeds a crop's critical temperature during flowering or
grain fill. A few kelvin of shade cooling across those days is worth more than
the light it costs. Chickpea is the clearest case.

There is a third thing, specific to the Konkan and easy to miss. Roha takes
2500 mm of rain in four months and then goes dry, so a large share of the
district lies **rabi fallow** from October to June. The counterfactual for a
winter crop there is not a smaller harvest — it is bare ground. The array pays
for the farm pond and the drip that make a second crop possible at all. Total
food output at Roha rises 7.9% while the parcel additionally delivers 4.7 GWh.

Land equivalent ratio cannot express that, because it divides, and the
denominator is zero. `metrics.system_comparison` reports it as absolute
quantities instead, and `land_equivalent_ratio` returns `None` rather than
inventing a spectacular number.

---

## Quick start

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
agrivolt run scenarios/roha-konkan.yaml --out out/roha.json
```

Weather is fetched from NASA POWER on first run and cached under `data/cache`,
so every subsequent run is offline and byte-identical.

Sweep the design variable that actually matters:

```bash
agrivolt sweep scenarios/roha-konkan.yaml --pitch 6:20:1
```

List the crop library:

```bash
agrivolt crops
```

---

## How it works

A pipeline of small stages. Nothing below a stage imports anything above it, so
each can be exercised alone.

```
site + array geometry
    ├── irradiance   split GHI into beam and diffuse (Erbs)
    ├── shading      how much light clears the array and reaches the canopy
    ├── pv           bifacial generation, Faiman cell temperature, PVWatts DC
    ├── water        FAO-56 Penman-Monteith, open field and shaded
    ├── crop         yield response to light, water and heat
    ├── economics    two revenue streams, LCOE, NPV, IRR, breakeven tariff
    └── metrics      land equivalent ratio, absolute system comparison
```

`scenario.run` composes them. If a calculation is happening in `scenario.py`
rather than being delegated to a stage, that is a bug.

The light model is the only part that is genuinely novel, so it carries the most
tests. A tilted row of slant width `W` casts a shadow of width
`W·|cos(tilt) + sin(tilt)·tan(φ)|` perpendicular to the rows, where `φ` is the
solar zenith projected onto that plane. Dividing by pitch gives the shaded
ground fraction directly. That derivation is written out in `shading.py` rather
than being called out of a library, and `tests/test_shading.py` pins it against
pvlib's independent implementation to twelve decimal places.

One result from that model is worth stating because it contradicts a common
intuition: **clearance height does not increase the light reaching the crop.**
For an infinite row array the mean sky view factor is set by ground coverage
ratio; raising the array only distributes the same deficit more evenly. Height
is bought for tractor access and for uniformity, not for total light. A test
asserts this, because the first version of that test asserted the opposite and
was wrong.

---

## What is solid and what is not

Being clear about this is the difference between a model and a brochure.

**Solid.** The PV side is conventional pvlib and would survive a lender's
technical review. The light model agrees with pvlib's independent
implementation. FAO-56 is implemented in full and checked against published
reference values. The tariff is a real MERC order. Every financial assumption
lives in `config/assumptions.yaml` with a source and a confidence level, and
none is hard-coded in Python.

**Not solid.** Crop parameters in `config/crops.yaml` are literature midpoints
and district averages, not calibrations against the Roha site. They are good
enough to rank designs against each other and not good enough to quote a single
absolute yield. The three yield channels are combined multiplicatively as
though independent, which they are not — water and heat stress compound. That
assumption is conservative for the agrivoltaic case, so it understates rather
than inflates the argument.

Weather is reanalysis, not ground measurement, because rural Maharashtra has
essentially no public hourly irradiance record. Mandi prices come from a
snapshot endpoint that only serves the current day, so the crop revenue line
currently uses minimum support price as a conservative floor.

The Roha coordinates in `scenarios/roha-konkan.yaml` are a placeholder pending
the parcel survey and are marked as such.

---

## Data sources

| Source | Used for | Access |
|---|---|---|
| [NASA POWER](https://power.larc.nasa.gov/) | Hourly irradiance, daily meteorology | Open, no key |
| [MERC](https://merc.gov.in/) | MSKVY 2.0 tariff order, 5 Aug 2026 | Public order |
| [Agmarknet via data.gov.in](https://data.gov.in/) | Mandi prices | Open, key required |
| [pvlib](https://pvlib-python.readthedocs.io/) | PV and view factor models | BSD |
| FAO-56 / FAO-33 | Evapotranspiration, yield response | Published |

---

## Roadmap

1. **Replace the crop model with AquaCrop.** The current three-factor model is
   defensible and transparent, but a coupled daily water-and-canopy simulation
   is what a reviewer will want. `aquacrop` covers paddy, soybean, sorghum,
   cotton and wheat; onion and grapes will need the simpler model to remain.
2. **Calibrate against the Roha site.** Everything above is uncalibrated. One
   season of measured yield and soil moisture changes the standing of every
   number in this repository.
3. **Accumulate the mandi price archive.** The Agmarknet endpoint serves only
   today, so a daily cache compounds into a dataset that does not otherwise
   exist publicly.
4. **Spatial PAR with `bifacial_radiance`.** Ray-traced light distribution under
   the array, rather than a row-averaged transmission ratio — the difference
   between "70% of light" and knowing which rows of crop get it.
5. **Farmer-side economics.** The project pro-forma here is the developer's.
   Under MSKVY the farmer's position is different, and it is the one that
   determines whether land is available at all.

---

## Licence

MIT. See [LICENSE](LICENSE).
