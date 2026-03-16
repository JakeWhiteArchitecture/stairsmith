"""
IFC Staircase Generator — Flask Application

A locally-hosted web application that generates valid IFC 2x3 files
for parametric staircases (straight, single-winder, double-winder).
"""

import os
from datetime import date
from flask import Flask, render_template, request, jsonify, send_file
from ifc_generator import meshes_to_ifc
from stair_preview import generate_preview_geometry

app = Flask(__name__)


@app.route("/")
def index():
    response = render_template("index.html")
    from flask import make_response
    resp = make_response(response)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/stair_preview.py")
def serve_stair_preview():
    """Serve stair_preview.py so the Pyodide frontend can fetch it."""
    from flask import send_from_directory
    resp = send_from_directory(os.path.dirname(__file__), "stair_preview.py",
                               mimetype="text/plain")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/ifc_generator.py")
def serve_ifc_generator():
    """Serve ifc_generator.py so the Pyodide frontend can fetch it for IFC export."""
    from flask import send_from_directory
    resp = send_from_directory(os.path.dirname(__file__), "ifc_generator.py",
                               mimetype="text/plain")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/dxf_generator.py")
def serve_dxf_generator():
    """Serve dxf_generator.py so the Pyodide frontend can fetch it for DXF export."""
    from flask import send_from_directory
    resp = send_from_directory(os.path.dirname(__file__), "dxf_generator.py",
                               mimetype="text/plain")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/StairSmith-Logo.png")
def serve_logo():
    """Serve the StairSmith logo image."""
    from flask import send_from_directory
    return send_from_directory(os.path.dirname(__file__), "StairSmith-Logo.png",
                               mimetype="image/png")


@app.route("/api/preview", methods=["POST"])
def preview():
    """
    Return 3D geometry data as JSON for the Three.js preview.
    This generates the staircase geometry as mesh data without creating an IFC file.
    Also returns plan dimension data so the 3D viewer can show matching dimensions.
    """
    params = request.get_json()
    try:
        geometry = generate_preview_geometry(params)
        # Compute plan dimensions (same logic as DXF output)
        try:
            from dxf_generator import _compute_plan_dimensions
            dims = _compute_plan_dimensions(geometry, params, 0, 0)
            # Convert to simple format for JS: [{p1:[x,y], p2:[x,y], label:str}]
            import math
            dim_data = []
            for d in dims:
                length = math.hypot(d["p2"][0] - d["p1"][0],
                                    d["p2"][1] - d["p1"][1])
                lbl = d.get("label") or ("%.0f" % length)
                dim_data.append({
                    "p1": list(d["p1"]),
                    "p2": list(d["p2"]),
                    "label": lbl,
                })
        except Exception:
            dim_data = []
        return jsonify({"success": True, "geometry": geometry,
                        "dimensions": dim_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/download", methods=["POST"])
def download():
    """Generate and download an IFC file.

    Uses the same preview geometry as the 3D preview, converted to IFC.
    This guarantees the IFC file matches what the user sees on screen.
    """
    params = request.get_json()
    try:
        meshes = generate_preview_geometry(params)
        filepath = meshes_to_ifc(meshes)
        today = date.today().strftime("%d-%m-%y")
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f"StairSmith_{today}_1.ifc",
            mimetype="application/x-step",
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/download_dxf", methods=["POST"])
def download_dxf():
    """Generate and download a DXF plan-view file."""
    from dxf_generator import meshes_to_dxf
    params = request.get_json()
    try:
        meshes = generate_preview_geometry(params)
        filepath = meshes_to_dxf(meshes, params)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f"StairSmith_{date.today().strftime('%d-%m-%y')}_1.dxf",
            mimetype="application/dxf",
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
