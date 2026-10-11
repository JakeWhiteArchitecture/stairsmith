# StairSmith: setup wizard and save/open

Build a step-by-step setup wizard into StairSmith (`app.html`), plus Save and Open for a stair as a JSON file. Reference sketches for every wizard step are in `sketches/`, and the script that draws them is `make_sketches.py`. Read this whole document before starting, then work in the passes set out at the end.

## Why

A new user currently faces the full parameter panel at once. The wizard walks them through the stair in a sensible order, one small set of inputs per step, each with a diagram that shows exactly what the inputs mean. The same wizard will later be ported to an IngeTrazo extension (a Python and Qt desktop modeller), so the wizard definition and the diagrams must live in shared Python, not in JavaScript.

## Architecture

1. **Wizard definition in Python.** A new module, `stair_wizard.py`, holds the steps as plain data: id, title, fields (parameter name, label, unit, default, min, max, step), and the rule that decides whether the step is shown. The JavaScript builds the wizard UI from this definition, read through Pyodide like the existing modules.
2. **Diagrams in Python, output as SVG text.** A new module, `stair_diagrams.py`, has one function per step that takes the current parameter set and returns an SVG string. The browser drops the string into the wizard. Later, the IngeTrazo version will display the same SVG strings in Qt, so no diagram logic may live in JavaScript.
3. **Diagrams never work out the stair themselves.** From step 2 onwards, every diagram is drawn from StairSmith's own computed geometry: tread count per flight, winder positions, landing sizes, newel positions, rise and pitch. Take these from the same Python that builds the 3D (`stair_flights.py`, `stair_winder_geometry.py`, `_parse` in `stair_constants.py`). If the geometry is currently computed inline, expose it through a small function that returns the values rather than duplicating the sums in the diagram code. The drawing in the wizard and the 3D model behind it must always agree.
4. **Start from `make_sketches.py`.** It already has the drawing helpers (lines, oblique dimensions, plan drawing with balustrades, newels, clipped wall hatch, winder set-out) and the palette. Port these into `stair_diagrams.py`. Where the sketch script uses typed-in flight counts (9 + 3 for the L, 5 + 2 + 5 for the U, 6 + 6 for the half-landing), replace them with the counts StairSmith computes.

## Wizard behaviour

- Opens on page load, straight after the Terms of Use are accepted.
- Everything behind it is faded, including the sidebar, and 3D navigation is locked while it is open. The StairSmith logo sits in the wizard's own header.
- The stair in the 3D preview updates live behind the fade as values change, using the existing `updatePreview()`.
- An X button, top right, closes the wizard and loads the standard straight run with default values. The Escape key does the same. Clicking outside the wizard does nothing, so a stray click never loses the inputs.
- Back and Next at the bottom of every step. Back is hidden on the first step. On the last applicable step, Next becomes **Finish**, which closes the wizard and keeps everything entered.
- A step indicator across the top shows only the steps that apply to the chosen stair type. Steps already visited can be clicked to jump back.
- A **Stair wizard** button in the sidebar reopens the wizard, pre-filled with the current settings.
- The wizard and the sidebar always hold the same values. Changing one updates the other.

## The steps

Parameter names are those used by `getParams()` and `_parse()`.

### 0. Stair type
- Inputs: `staircase_type` (Straight Flight, Single Winder (L-shape), Double Winder (U-shape), Half-Landing (U-shape)), and the hand, using the existing mirror logic (`turn1_direction`, `turn2_direction`).
- Keep the existing type names.
- Diagram: one small plan icon per type, the selected one in the accent colour, arrows showing the line of travel. These are fixed icons and do not follow the parameters. Turning types are drawn with flat landings at the corners (no winders), and the Double Winder icon shows the short middle flight running between its two landings. See `sketches/step0_stair_type.svg`.

### 1. Height
- Input: `floor_to_floor`.
- Diagram: a fixed section through a simple two-storey house, with a straight stair starting 1 m off the inside face of the external wall. Walls, floors, roof and ground read as one mass, with no lines at the junctions. Only the floor-to-floor figure on the dimension updates; the drawing itself stays the same. See `sketches/step1_height.svg`.

### 2. Risers and going
- Inputs: `num_risers`, `going`, `nosing`.
- Reference values, shown in grey and recalculated live: rise (floor-to-floor divided by risers), treads (risers minus one), pitch.
- Diagram: a section of three steps drawn from the live values, so a steeper stair looks steeper. The going is dimensioned nosing to nosing. See `sketches/step2_risers_and_going.svg`.

### 3. Treads and risers
- Inputs: `tread_thickness`, `riser_thickness`.
- Diagram: one tread and riser, close up in section, set within the flight: the tread runs its full going back to the next riser, which rises off its back edge, and the tread below continues, both cut open. See `sketches/step3_treads_and_risers.svg`.

### 4. Width, sides and newels
- Inputs: `stair_width`, `left_condition`, `right_condition` (wall or balustrade), `newel_size`.
- Diagram: the whole stair in plan, in the type chosen on step 0, with flat landings at the corners. It redraws as the side toggles change.
  - Balustrade drawn as two lines (the handrail width), centred on the newels, with newels at the start, at each corner and at the end.
  - Treads and landing edges stop at the inner balustrade line. No line is drawn outside the handrail.
  - Walls drawn as a solid line with hatching outside, clipped so the hatch never crosses a tread.
  - Width dimensioned across the first flight, outside to outside.
  - See `sketches/step4_width_sides_newels.svg` and, with the sides swapped, `sketches/step4_width_sides_newels_inverted.svg`.
- Half-landing rule: when the inner side is set to wall, raise the minimum `newel_to_newel` to `newel_size + 100`, so a 100 mm wall fits between the flights, and push the current value up to it if needed. When the inner side goes back to balustrade, the minimum returns to the existing `newel_size + 50`.

### 5. Corners (Single Winder and Double Winder only)
- Inputs: Winders or Flat landing for each corner (`turn1_enabled`, `turn2_enabled`; true means winders), then treads per flight (`flight1_steps`, `flight2_steps`, `flight3_steps`).
- In the wizard, corners start as **flat landings**. Note that the sidebar currently defaults them to winders; the wizard overrides that.
- Diagram: the whole stair in plan with each corner numbered in walking order, outside the plan. Clicking a corner on the plan toggles it, as well as the toggle buttons. The toggles match the sidebar's existing corner buttons.
- Treads per flight sits under the toggles, reusing the existing `transferStep()` logic and its limits. It starts on the automatic split. In the wizard the counts are cyan and the arrow buttons are wider than in the sidebar; leave the sidebar version as it is.
- The plan redraws as corners toggle and steps move, always from StairSmith's computed geometry. Indicative winder lines on this plan start at the X marks on the newel faces, as on step 6.
- See `sketches/step5_corners.svg`.
- For the Half-Landing type, step 5 instead shows `newel_to_newel` (centre to centre) and the landing oversize. See `sketches/step5_corners_half_landing.svg`.

### 6. Winder set-out (only when at least one corner has winders)
- Inputs: `winder_x`, `winder_y`, entered once for all winder corners.
- Diagram: a cropped close-up round the newel at a quarter turn. X and Y are dimensioned down the newel face from its inside corner. Winder lines start at the X marks. The flights meet the newel at the Y marks, matching how `stair_flights.py` shifts flight 1 (`flight1_shift_y = hp - wx - wy + nosing`). See `sketches/step6_winder_set_out.svg`.

### Step order and skipping
- Straight: 0, 1, 2, 3, 4, then Finish.
- Single and Double Winder: 0 to 5, plus 6 only if a corner has winders.
- Half-Landing: 0 to 5 (step 5 in its half-landing form).

### Not in the wizard
Threshold depth and the balustrade sizes (handrail, baserail, spindle) stay at their defaults and remain adjustable in the sidebar after Finish.

## Save and Open

Separate from the wizard, in the sidebar next to the export buttons:

- **Save stair** downloads a JSON file holding everything `getParams()` returns, wrapped as `{"format": "stairsmith-stair", "version": 1, "params": {...}}`.
- **Open stair** loads such a file, checks the format and version, passes the values through `_parse()` so out-of-range values are clamped, updates the sidebar and redraws the preview. If the file is not a StairSmith stair, say so plainly and change nothing.
- The IngeTrazo extension will later use the same JSON, stored on the stair group so a stair can be reopened for editing.

## Drawing style

Match the sketches. All colours are named constants in `make_sketches.py`; keep them as constants in `stair_diagrams.py`.

- Background is the wizard panel colour `#16213e` (the page behind is `#1a1a2e`, borders `#0f3460`).
- **Cyan `#00ccff`** for whatever the current step sets, with `#4fdcff` for cyan text.
- Light grey `#c9c9d4` for context linework, `#e0e0e0` for headings.
- Muted blue-grey `#8a93ad` for dimensions, projection lines and reference values.
- Wall hatch `#5b6688`. Newels are filled with the panel colour so lines behind them are hidden.
- Mock UI controls follow the app: active toggle `#e94560` with white text, inactive `#1a1a2e` with `#aaa` text.
- Dimensions use the oblique style: a 45 degree tick at each end, the line running slightly past the ticks, no arrows, and the figure close to the line.
- System font stack, as in the app.

## Wording

- Rise, pitch and the other reference values are for information only. The wizard must not suggest that it checks the stair against Approved Document K or any other regulation: no ticks, "compliant" labels or pass/fail colours.
- Keep labels short and plain.

## Passes

Work in passes. Each pass should leave StairSmith working.

1. **Pass 1:** `stair_wizard.py` with the full step definition; the wizard shell (fade, locked navigation, X, Escape, Back/Next, step indicator, Finish, live preview, sidebar sync); steps 0 and 1 with their diagrams from `stair_diagrams.py`.
2. **Pass 2:** steps 2 and 3.
3. **Pass 3:** step 4, including the half-landing wall rule, and the function that exposes StairSmith's computed geometry for the diagrams.
4. **Pass 4:** steps 5 and 6.
5. **Pass 5:** Save stair and Open stair.

## Checks before finishing each pass

- For each stair type, the number of treads in each flight drawn in the wizard matches the 3D model, including after toggling corners and moving steps.
- The X button and Escape both load the default straight run.
- Values set in the wizard appear in the sidebar, and changes in the sidebar appear when the wizard is reopened.
- A saved file reopens to the identical stair.
- The sidebar's own controls still behave exactly as before.
