<div align="center">
  <img src="StairSmith-Logo.png" alt="StairSmith" width="280">

  # StairSmith

  **A free, browser-based parametric staircase design tool.**

  Model straight and winder timber staircases in 3D, then export IFC4 models and dimensioned DXF drawings — no install, no login, no backend.

  [Launch the tool »](https://jakewhitearchitecture.com/stairsmith/)
</div>

---

## What it does

StairSmith lets you set out residential timber staircases parametrically and see them update live in 3D:

- **Layouts** — straight flights, 90° single‑winder turns, and 180° double‑winder turns
- **Traditional kite winder setting‑out** with newel posts, stringers and balustrade
- **Live 3D preview** with orbit, measure and dimension tools, plus an auto‑rotate view
- **Reference values** — rise, going, pitch and 2R+G are shown to assist the designer
- **IFC4 export** — a proper spatial model (project → site → building → storey → stair) with materials, property sets, stable GUIDs and Uniclass 2015 classification, for BIM coordination
- **DXF export** — dimensioned plan, four elevations and stepped sections

> [!IMPORTANT]
> **StairSmith does not check or assure compliance.** It is a design aid — it will happily let you model a staircase that is right or wrong, and the design remains entirely your responsibility. All outputs must be independently checked and verified by a competent person before any use. Reference values shown in the tool are for information only.

## How it works

StairSmith is a **fully static site** — everything runs in the browser, with no server-side compute.

| Layer | Technology |
|-------|------------|
| UI & 3D viewport | HTML/CSS/JS + [Three.js](https://threejs.org/) r128 |
| Geometry engine | Python, run in the browser via [Pyodide](https://pyodide.org/) (CPython compiled to WebAssembly) |
| 2D geometry | [Shapely](https://shapely.readthedocs.io/) (GEOS) for DXF sections, elevations and winder set-out |
| IFC authoring | [IfcOpenShell](https://ifcopenshell.org/) (WASM wheel) |

The same Python modules that power the live preview also produce the DXF and IFC exports — the UI hands a parameter set to Python, which returns a shared mesh list consumed identically by the preview, the DXF generator and the IFC generator.

```
index.html   →  SEO landing page + Terms of Use gate
app.html     →  the tool (Three.js viewport, controls, Pyodide bootstrap)

stair_preview.py          façade: params → mesh list
├─ stair_constants.py     parsing, box meshes, colour → IFC-type map
├─ stair_flights.py       straight / single-winder / double-winder layouts
├─ stair_winder_geometry.py   kite winder set-out and winder risers
└─ stair_balustrade.py    stringers, handrails, baserails, spindles, newels

dxf_generator.py   mesh list → DXF (plan, elevations, sections)
ifc_generator.py   mesh list → IFC4 model
```

See [`docs/stairsmith-architecture.drawio`](docs/stairsmith-architecture.drawio) for a full build diagram.

## Running locally

Because the page fetches the Python modules at runtime, it must be served over HTTP (opening `index.html` from the filesystem will not work). Any static file server will do:

```bash
git clone https://github.com/JakeWhiteArchitecture/3Dstaircreator.git
cd 3Dstaircreator
python3 -m http.server 8000
```

Then open <http://localhost:8000/index.html>. Pyodide, Three.js and the IfcOpenShell wheel are loaded from CDNs, so an internet connection is required on first load.

## Project structure

| Path | Purpose |
|------|---------|
| `index.html` | Landing page and Terms of Use gate |
| `app.html` | The tool — viewport, controls, and Pyodide bootstrap |
| `stair_preview.py` | Entry point: turns parameters into the shared mesh list |
| `stair_constants.py` | Parameter parsing, box meshes, colour/IFC-type mapping |
| `stair_flights.py` | Per-type flight layout (straight / single / double winder) |
| `stair_winder_geometry.py` | Kite winder setting-out and winder risers |
| `stair_balustrade.py` | Stringers, handrails, baserails, spindles, newels |
| `dxf_generator.py` | DXF plan / elevation / section export |
| `ifc_generator.py` | IFC4 model export |
| `docs/` | Architecture diagram and IFC delivery checklist |

## License

Licensed under the [Apache License 2.0](LICENSE).

If you reuse or build on this code, please retain the [`NOTICE`](NOTICE) file and acknowledge the original repository:

> StairSmith — https://github.com/JakeWhiteArchitecture/3Dstaircreator

## Credits

Built by [Jake White Architecture](https://www.jakewhitearchitecture.com). Inspiration for the tool came out of a group discussion with the ATPT (Architectural Technologist Power Team).

If you find StairSmith useful, you can [buy me a coffee](https://buymeacoffee.com/jakewhite) ☕
