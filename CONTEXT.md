# CONTEXT — 3Dstaircreator domain

This file pins the domain vocabulary used across the codebase. Use these
terms exactly in code, comments, and docs. Add to this file when a new
domain concept is named; sharpen entries when a term gets fuzzy in
discussion.

## Terms

- **Staircase** — the whole thing. One or more *flights* joined by *winders*,
  with *treads*, *risers*, *stringers*, *newels*, and a *balustrade*.

- **Flight** — a straight run of treads between two landings or winder
  turns. A staircase has 1 flight (straight), 2 (single winder), or 3
  (double winder).

- **Winder** — a triangular or kite-shaped tread that turns the staircase
  90°. Multiple winders form one turn between flights.

- **Tread** — the horizontal surface you step on.

- **Riser** — the vertical face between two consecutive treads.

- **Stringer** — the structural board on each side that the treads attach
  to. Has wall-side and balustrade-side variants.

- **Newel** — a square post at top, bottom, and at each turn. Anchors the
  *handrail* and *baserail*. Square cross-section, parameter `newel_size`.

- **Balustrade** — the railing assembly: *handrail* + *baserail* + spindles.

- **Handrail** — the top rail you grip, mounted on the *newels* above the
  flight at hand-height.

- **Baserail** — the bottom rail running parallel to the handrail; spindles
  attach between handrail and baserail.

- **Layout** — *(planned — see `/tmp/architecture-review-*.html` Candidate 1)*
  the value object holding all staircase positions, profiles, and extents
  in stair-local coordinates, independent of output format. Not yet a
  module — geometry is currently re-computed inside each generator.
