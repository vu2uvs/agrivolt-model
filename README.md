# agrivolt-model

Working out whether it makes sense to grow crops underneath solar panels in
India, and putting real numbers on the answer.

Agrivoltaics means mounting a solar array high enough that a tractor can drive
under it, so the same hectare produces electricity and food. Whether that is
worth doing depends on how much light the crop loses, how much water it saves,
and what the electricity sells for. All three are different in Solapur than they
are in Bavaria, which is why this model exists.

Everything here runs on public data. No figure in this README is typed in by
hand, and every one of them can be reproduced with a single command.

## What we found

Seven scenarios across Maharashtra and Karnataka, five weather years each, on a
15 acre parcel.

| Site | Agro-climatic zone | LER | kWh/kWp | Crop margin ₹/yr | Breakeven ₹/kWh |
|---|---|---:|---:|---:|---:|
| Nashik | Assured rainfall, horticultural | 1.60 | 1776 | +700,550 | 3.235 |
| Solapur | Scarcity zone, semi-arid | 1.58 | 1830 | +65,642 | 3.361 |
| Kalaburagi | North interior Karnataka, semi-arid | 1.50 | 1811 | +79,209 | 3.369 |
| Yavatmal | Vidarbha dryland | 1.46 | 1735 | +104,772 | 3.477 |
| Yavatmal, late sown | Vidarbha dryland, Dec sowing | 1.46 | 1735 | +340 | 3.508 |
| Roha, Raigad | Konkan coastal, 2500 mm rain | 1.45 | 1760 | +71,725 | 3.489 |
| Nagpur | Vidarbha, cotton | 1.43 | 1713 | +174,337 | 3.487 |

### What those columns mean

If you have not met these numbers before, here is the plain version.

**LER, or Land Equivalent Ratio.** How much land you would need to produce this
much food and this much electricity separately. An LER of 1.5 means one hectare
of agrivoltaics does the work of one and a half hectares split between a farm
and a solar farm. Anything above 1.0 is a gain. Our sites land between 1.43 and
1.60, which is in line with the international field trials.

**kWh/kWp.** How many units of electricity a year each unit of installed panel
capacity produces. It is the standard way to compare one solar site against
another regardless of project size. Indian projects typically run somewhere
between 1400 and 1900. Sunny, dry Solapur tops our list at 1830 and cloudier
Nagpur sits lowest at 1713.

**Crop margin ₹/yr.** What the farming side clears in a year after paying for
seed, labour and everything else, across the whole 15 acre plot. Worth noticing
how small this is next to the electricity revenue, which runs to well over a
crore. The crop is not what pays for the project, and pretending otherwise would
be dishonest.

**Breakeven ₹/kWh.** The price the electricity has to sell at for the project to
earn an 11% return, which is roughly what an Indian renewables lender expects.
This is the number the whole repository is really about.

### The headline

> Every site needs between ₹3.24 and ₹3.51 per unit to make the numbers work.
> Maharashtra's MSKVY 2.0 scheme currently pays ₹2.825.

That is a shortfall of 41 to 68 paise per unit, and it holds across every site,
every crop, and the whole range of build costs the market plausibly offers. No
combination of a realistic 2026 capex and any tariff MERC actually discovered
across the 257 MSKVY substations closes it.

So the interesting question is not whether agrivoltaics works agronomically in
India. On these numbers it does. The problem is that the state's flagship
decentralised solar scheme is priced for conventional ground mount, and the
extra cost of building high enough to farm underneath is currently unfunded.
That is a policy gap with a number attached, and a number is a far more useful
thing to bring to a conversation than an opinion.

## Why India is not Bavaria

Most published agrivoltaics research comes from Germany, France and the United
States. It carries an assumption from those climates, which is that shade costs
yield and you accept the cost because the electricity is worth more. Under a
European light budget that is correct. Under an Indian one it can invert, and
the model shows exactly where.

**Shade helps the crop that is already struggling.** Late sown chickpea in the
hot dry interior is short of both water and cool weather, and the array supplies
both at once. At Kalaburagi it yields 0.56 t/ha under the panels against 0.44 in
the open, a gain of 27%. Relative transpiration rises from 0.46 to 0.64 and the
heat stress factor improves from 0.80 to 0.89. The same crop at Yavatmal gains
25%.

**Shade hurts the crop that is already comfortable.** Cotton at Nagpur loses
23%, monsoon paddy at Roha loses 21%, kharif soybean loses 20%. These grow
through the rains with plenty of water and moderate temperatures, so the light
the array takes is simply gone.

That split is the finding. Agrivoltaics in India is not a general improvement,
it is a targeted one, and the targeting is predictable from climate and sowing
date.

**Sowing date matters more than the array does.** Chickpea sown in late October
fills grain through a mild December and never meets heat stress at all, so the
array's cooling is worth nothing to it. Sown on 5 December, which is the norm
across Vidarbha because rabi planting waits on the soybean harvest, grain fill
moves into March and runs above 35 °C on half of all days. Moving the sowing
date three weeks earlier is worth roughly three times what the panels are.

**Sometimes the land grows nothing at all.** Roha takes 2500 mm of rain in four
months and then goes dry, so much of Raigad lies fallow from October to June.
A winter crop there is not a smaller harvest, it is a harvest that does not
currently exist. Total food output at Roha rises 8.1% while the parcel also
delivers 4.8 GWh. It is the only site in the set where food output goes up.
Everywhere else it falls, by between 1% and 23%, and the model says so plainly
rather than burying it.

Land Equivalent Ratio cannot express the Roha case, because it divides and the
denominator is zero. So `metrics.system_comparison` reports the same comparison
in absolute tonnes, and `land_equivalent_ratio` returns `None` rather than
inventing a spectacular number.

## Running it

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
agrivolt run scenarios/roha-konkan.yaml --out out/roha.json
```

Weather comes from NASA POWER on the first run and is cached under `data/cache`,
so every run after that is offline and gives byte identical results.

Sweep the one design variable that really matters, which is how far apart the
rows are.

```bash
agrivolt sweep scenarios/roha-konkan.yaml --pitch 6:20:1
```

Produce the time resolved curves used for plotting.

```bash
agrivolt profiles scenarios/roha-konkan.yaml --out out/profiles.json
```

List the crop library.

```bash
agrivolt crops
```

## How it works

A pipeline of small stages. Nothing lower down imports anything higher up, so
each stage can be exercised on its own.

```
site + array geometry
    ├── irradiance   split sunlight into direct beam and diffuse sky
    ├── shading      how much light clears the array and reaches the crop
    ├── pv           bifacial generation, cell temperature, DC to AC losses
    ├── water        FAO-56 evapotranspiration, open field and shaded
    ├── crop         yield response to light, water and heat
    ├── economics    two revenue streams, LCOE, NPV, IRR, breakeven tariff
    └── metrics      land equivalent ratio, absolute system comparison
```

`scenario.run` composes them. If a calculation is happening in `scenario.py`
rather than in one of the stages, that is a bug.

The light model is the only genuinely novel part, so it carries the most tests.
A tilted row of slant width `W` casts a shadow of width
`W·|cos(tilt) + sin(tilt)·tan(φ)|` measured across the rows, where `φ` is the
solar zenith projected onto that plane. Divide by the row spacing and you have
the shaded ground fraction directly. That derivation is written out in
`shading.py` rather than called out of a library, and `tests/test_shading.py`
pins it against pvlib's independent implementation to twelve decimal places.

One result from it contradicts a common intuition, so it is worth stating.
**Raising the array does not give the crop more light.** For a long run of
parallel rows, the average light reaching the ground is set by how much of the
ground the panels cover, and lifting them only spreads the same shortfall more
evenly. Height buys tractor access and uniform shade, not more sunlight. There
is a test asserting this, because the first version of that test asserted the
opposite and was wrong.

## What is solid and what is not

Being clear about this is the difference between a model and a brochure.

### Solid

The solar side is conventional pvlib and would survive a lender's technical
review. The light model agrees with pvlib's independent implementation. FAO-56
evapotranspiration is implemented in full and checked against published
reference values. The tariff comes from a real MERC order dated 5 August 2026.

Every financial assumption lives in `config/assumptions.yaml` with a source and
a confidence level attached, and none of them is hard coded in Python. If you
disagree with the case, the argument should be about a line in that file.

Sunlight and sun position are checked against each other directly.
`tests/test_sources.py` asserts that peak measured irradiance falls within an
hour of the sun being highest. That test exists because the first version of
this model failed it. NASA POWER serves Local Solar Time by default, the loader
labelled it UTC, and every hour of sunlight was paired with a sun position five
hours out. It still produced a believable annual total the whole time, which is
exactly why it needed a test rather than a glance.

### Not solid

Crop parameters in `config/crops.yaml` are literature midpoints and district
averages, not calibrations against any of these sites. They are good enough to
rank designs against each other and not good enough to quote a single absolute
yield.

The three yield channels (light, water, heat) are multiplied together as though
independent, which they are not. Water stress and heat stress compound in
reality. That assumption understates the agrivoltaic case rather than inflating
it, so the error runs in the conservative direction.

Soil water carried into the season is set per site from soil type rather than
measured, and it matters a great deal. Adding it moved several sites from
apparently failing to comfortably profitable, because rabi farming across the
Deccan runs on monsoon water stored in the soil profile, and a balance counting
only in-season rain concludes those crops fail completely.

Weather is reanalysis rather than ground measurement, because rural India has
almost no public hourly sunlight record. Mandi prices come from a feed that
serves only the current day, so crop revenue currently uses minimum support
price as a conservative floor.

The Roha coordinates in `scenarios/roha-konkan.yaml` are a placeholder pending
the site survey, and are marked as such in the file.

## Data sources

| Source | Used for | Access |
|---|---|---|
| [NASA POWER](https://power.larc.nasa.gov/) | Hourly sunlight, daily weather | Open, no key |
| [MERC](https://merc.gov.in/) | MSKVY 2.0 tariff order, 5 Aug 2026 | Public order |
| [Agmarknet via data.gov.in](https://data.gov.in/) | Mandi prices | Open, key required |
| [pvlib](https://pvlib-python.readthedocs.io/) | Solar position, view factors, PV models | BSD |
| FAO-56 and FAO-33 | Evapotranspiration, yield response to water | Published |

## Roadmap

1. **Replace the crop model with AquaCrop.** The current three factor model is
   transparent and defensible, but a coupled daily water and canopy simulation
   is what a reviewer will want. The `aquacrop` package covers paddy, soybean,
   sorghum, cotton and wheat. Onion and grapes would stay on the simpler model.
2. **Calibrate against the Roha site.** Everything above is uncalibrated. One
   season of measured yield and soil moisture changes the standing of every
   number here.
3. **Measure soil water rather than assuming it.** It turned out to be one of
   the most influential inputs in the model and is currently a per site estimate.
4. **Build the mandi price archive.** The Agmarknet feed serves only today, so a
   daily cache compounds into a dataset that does not otherwise exist publicly.
5. **Spatial light mapping with `bifacial_radiance`.** Ray traced light under the
   array rather than a row averaged figure, which is the difference between
   knowing the crop gets 70% of the light and knowing which rows get it.
6. **Farmer side economics.** The pro forma here is the developer's. Under MSKVY
   the farmer's position is a different calculation, and it is the one that
   decides whether land is available at all.

## Licence

MIT. See [LICENSE](LICENSE).
