# DXF Plan View Export — Implementation Plan

## Overview

Add a "Download DXF" button alongside the existing IFC download. When clicked, generate a 2D plan-view DXF file directly from the same staircase parameters (not from the IFC model or 3D mesh data). The DXF generator re-computes XY coordinates using the same parameter logic as `stair_flights.py`, but only outputs 2D lines at Z=0.

## Architecture Decision: Raw DXF Text (No ezdxf dependency)

**Why not ezdxf in Pyodide?** The `ezdxf` library has dependencies on `numpy` and `fontTools` with optional C extensions. While it *might* work in Pyodide, the spec says: "If it doesn't work in Pyodide, generate raw DXF text directly." To avoid runtime dependency issues and keep the module lightweight (no `micropip.install` step needed), we will **generate raw DXF text directly** using a small helper class. This mirrors the pattern of keeping modules self-contained.

The DXF R2010 format is well-documented ASCII text. For plan-view lines and polylines, we only need:
- HEADER section (version, units)
- TABLES section (linetypes, layers)
- ENTITIES section (LINE and LWPOLYLINE entities)

This approach:
- Zero external dependencies — loads instantly (no `ensureEzdxf()` wait)
- Works in any Python environment (Pyodide, CPython, PyPy)
- File stays small since we only emit what's needed

## Files to Create/Modify

### 1. NEW: `dxf_generator.py` (~400-500 lines)

Pure Python module that generates DXF plan-view text from staircase parameters.

#### Module Structure

```
dxf_generator.py
├── class DxfWriter           # Low-level DXF text builder
│   ├── __init__()            # Sets up sections, handle counter
│   ├── _header()             # HEADER section (version R2010, mm units)
│   ├── _add_linetype()       # Define CONTINUOUS and DASHED linetypes
│   ├── _add_layer()          # Define a layer with colour and linetype
│   ├── add_line()            # Add LINE entity to ENTITIES section
│   ├── add_lwpolyline()      # Add LWPOLYLINE entity (closed or open)
│   └── save()                # Assemble full DXF string, write to file
│
├── meshes_to_dxf(meshes, params) -> str   # Public entry point
│   ├── _extract_params()     # Parse side conditions, dimensions
│   ├── _draw_straight()      # Straight staircase plan view
│   ├── _draw_single_winder() # L-shaped staircase plan view
│   └── _draw_double_winder() # U-shaped staircase plan view
│
└── Helper functions
    ├── _stringer_inner_x()   # Get inner face X of stringer at given side
    ├── _trim_line_to_x()     # Trim a horizontal line to X boundaries
    └── _trim_line_to_rect()  # Trim a line to a rectangle (newel post)
```

#### DxfWriter Class

Minimal DXF text generator. Manages:
- Handle counter (unique integer per entity, starting at 100)
- HEADER section: `$ACADVER` = AC1024 (R2010), `$INSUNITS` = 4 (mm), `$MEASUREMENT` = 1 (metric)
- TABLES section: LTYPE table (CONTINUOUS, DASHED), LAYER table (4 layers)
- ENTITIES section: LINE and LWPOLYLINE entities with layer, colour, linetype overrides

#### Geometry Generation Strategy

Rather than trying to extract 2D plan-view from the 3D mesh data (which stores centers/sizes in IFC coords), we **re-compute the 2D plan coordinates** from the same parsed parameters. This is actually simpler because:
- We only need XY positions, no Z at all
- The tread/riser/stringer X,Y positions are straightforward from `going`, `width`, `nosing`, etc.
- We can directly apply the trimming rules during generation

The function `meshes_to_dxf(meshes, params)` receives both the mesh list (for reference/cross-check) AND the raw params so it can compute plan geometry directly.

#### What Gets Drawn

**A. Straight Staircase**

For each tread `i` in `range(num_treads)`:
- **Nosing line** (front edge): horizontal line at `y = i * going - nosing + shift`
  - From `x = stringer_inner_left` to `x = stringer_inner_right`
  - Layer: STAIR_TREADS, colour 0, continuous
- **Back edge**: ONLY drawn for the LAST tread (top tread)
  - At `y = i * going - nosing + going + nosing + riser_t + shift` (= back of tread)
- **Riser line**: horizontal line at `y = i * going + shift`
  - Same X trim range as nosing
  - Layer: STAIR_RISERS, colour 9, DASHED linetype

For the first riser (i=0) and last riser (i=num_risers-1), also draw riser lines.

**Stringers** (left at x=0, right at x=width):
- Each stringer is a pair of parallel lines (inner face and outer face)
  - Inner face: `x = STRINGER_THICKNESS/2` (left) or `x = width - STRINGER_THICKNESS/2` (right)
  - Outer face: `x = 0` (left) or `x = width` (right)
  - Wait — actually stringer x_pos is 0 or width, with thickness centred on it, so:
    - Left stringer: outer at `x = -STRINGER_THICKNESS/2`, inner at `x = STRINGER_THICKNESS/2`
    - Right stringer: inner at `x = width - STRINGER_THICKNESS/2`, outer at `x = width + STRINGER_THICKNESS/2`
  - But note: `width = stair_width - STRINGER_THICKNESS`, so the full stair width includes stringers
- Y extent: from stringer start to stringer end (including extensions for wall condition)
- **Wall condition**: both lines solid, colour 0, layer STAIR_STRINGERS
- **Balustrade condition**:
  - Dashed (colour 9) where handrail runs above (raking flight portion)
  - Solid (colour 0) where beyond handrail (extensions, landings)

**Newel posts**: closed rectangle at each post position
- Centre at `(x_pos, y_pos)`, size `ns × ns`
- Layer: STAIR_HANDRAIL, colour 0, continuous
- Drawn as closed LWPOLYLINE (4 corners)

**B. Single Winder (L-shaped)**

Same as straight for Flight 1 and Flight 2 treads/risers, plus:

**Winder treads**: For each winder `i` in `range(actual_winders)`:
- The winder profile polygon is already computed by `_winder_profiles_from_construction()`
- In plan view, draw:
  - **Division lines** (the radiating edges between consecutive winders): solid, colour 0
    - These are the edges shared between adjacent winder profiles
    - Trim: inner end at newel post face, outer end at stringer inner face
  - **Outer nosing edge**: the curved/angled outer edge of the winder profile, solid, colour 0
  - **Back edge masking**: don't draw the back (upper) edge of a winder if the next tread/winder covers it

**Winder risers**: Already computed as `winder_polygon` meshes with profile coordinates
- Draw the front face line (nosing side) of each winder riser strip
- Dashed, colour 9, layer STAIR_RISERS

**Flight 2** runs perpendicular (in X direction):
- Nosing/riser lines are vertical in plan (parallel to Y axis)
- Same trimming logic but against Y-direction stringers

**C. Double Winder (U-shaped)**

Extension of single winder with two turns and three flights. Same logic applied to:
- Flight 1 (Y-direction), Turn 1 winders, Flight 2 (X-direction), Turn 2 winders, Flight 3 (Y-direction, reversed)

#### Trimming Implementation

All tread nosing/riser lines are drawn between stringer inner faces:
- For Y-direction flights: `x_left = STRINGER_THICKNESS/2`, `x_right = width - STRINGER_THICKNESS/2`
  - Actually: left stringer at x=0 has inner face at `x = STRINGER_THICKNESS/2`
  - Right stringer at x=width has inner face at `x = width - STRINGER_THICKNESS/2`
- For X-direction flights: same but in Y dimension, `y_inner = corner_y + STRINGER_THICKNESS/2`, `y_outer = corner_y + width - STRINGER_THICKNESS/2`

Winder division lines:
- Inner end: trimmed to newel post face (the face of the ns×ns rectangle nearest the winder)
- Outer end: trimmed to stringer inner face

### 2. MODIFY: `index.html`

#### A. Add "Download DXF" button (near line 824)

```html
<button class="btn btn-primary" onclick="downloadIFC();">Download IFC File</button>
<button class="btn btn-secondary" onclick="downloadDXF();" style="margin-top:8px;">Download DXF Plan</button>
```

#### B. Add `dxf_generator.py` to the Pyodide module loading list (near line 1888)

Add `'dxf_generator.py'` to the `stairModules` array so it's fetched and written to Pyodide's virtual filesystem on init.

#### C. Add `downloadDXF()` JavaScript function (near line 1876)

Follow the same pattern as `downloadIFC()`:
```javascript
async function downloadDXF() {
    if (!window.pyodideReady) { alert('Pyodide is still loading.'); return; }
    const params = getParams();
    const btn = /* find DXF button */;
    btn.textContent = 'Generating...';
    btn.disabled = true;
    try {
        const paramsJSON = JSON.stringify(params);
        const dxfProxy = await pyodide.runPythonAsync(`
import json as _json
from dxf_generator import meshes_to_dxf as _to_dxf
_p = _json.loads('''${paramsJSON}''')
_meshes = generate_preview_geometry(_p)
_path = _to_dxf(_meshes, _p)
with open(_path, 'rb') as _f:
    _data = _f.read()
import os; os.unlink(_path)
_data
`);
        const dxfBytes = dxfProxy.toJs();
        if (dxfProxy.destroy) dxfProxy.destroy();
        const blob = new Blob([dxfBytes], { type: 'application/dxf' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'staircase_plan.dxf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        alert('Error generating DXF: ' + err.message);
    } finally {
        btn.textContent = 'Download DXF Plan';
        btn.disabled = false;
    }
}
```

Key difference from IFC: **No `ensureIfcOpenShell()` call needed** — the DXF generator is pure Python with zero dependencies, already loaded at init time.

### 3. MODIFY: `app.py` (optional, for Flask route)

Add a `/api/download_dxf` route for server-side generation (mirrors the IFC endpoint). This is secondary — the primary path is client-side Pyodide.

## DXF Format Details

### Linetypes
- `CONTINUOUS`: Already standard, no pattern needed
- `DASHED`: Pattern `[6.35, 6.35, -3.175]` (total length, dash, gap) — standard architectural dash

### Layers
| Layer Name | Default Colour | Default Linetype | Purpose |
|---|---|---|---|
| STAIR_TREADS | 0 (BYBLOCK) | Continuous | Nosing lines, winder outer edges |
| STAIR_RISERS | 9 (grey) | DASHED | Riser lines |
| STAIR_STRINGERS | 0 | Continuous | Stringer outlines (per-entity overrides for dashed portions) |
| STAIR_HANDRAIL | 0 | Continuous | Newel post rectangles |

### Entity Colour/Linetype Overrides
For stringer lines under handrails (balustrade condition):
- Entity colour override: 9 (grey)
- Entity linetype override: DASHED
- These override the layer defaults on a per-entity basis

## Step-by-Step Implementation Order

1. **Create `dxf_generator.py`** with `DxfWriter` class and `meshes_to_dxf()` entry point
2. **Implement straight staircase** plan view first (simplest case)
3. **Implement single winder** plan view (adds winder division lines, perpendicular flight)
4. **Implement double winder** plan view (adds second turn, third flight)
5. **Modify `index.html`**: add button, module loading, download function
6. **Test** all three staircase types with various configurations
7. **Commit and push** to `claude/add-dxf-export-SKCVX`

## Risk Mitigation

- **ezdxf fallback**: If raw DXF proves insufficient for any reason, we can swap in ezdxf later since the public API (`meshes_to_dxf()`) stays the same
- **Coordinate verification**: The DXF generator uses the same `_parse()` and constants as the 3D engine, ensuring coordinates match
- **Testing**: Generate DXF for each staircase type and verify in a DXF viewer that lines align with the 3D preview
