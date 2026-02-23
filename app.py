"""
IFC Staircase Generator — Flask Application

A locally-hosted web application that generates valid IFC 2x3 files
for parametric staircases (straight, single-winder, double-winder).
"""

import os
import threading
from flask import Flask, render_template, request, jsonify, send_file
from ifc_generator import meshes_to_ifc
from stair_preview import generate_preview_geometry

app = Flask(__name__)

# ─── IFC DOWNLOAD COUNTER ───
_ifc_counter_lock = threading.Lock()
_ifc_counter = 0


def _get_ifc_count():
    global _ifc_counter
    # Try to load persisted count from file
    try:
        count_file = os.path.join(os.path.dirname(__file__), '.ifc_count')
        with open(count_file, 'r') as f:
            return int(f.read().strip())
    except Exception:
        return _ifc_counter


def _increment_ifc_count():
    global _ifc_counter
    with _ifc_counter_lock:
        count = _get_ifc_count() + 1
        _ifc_counter = count
        try:
            count_file = os.path.join(os.path.dirname(__file__), '.ifc_count')
            with open(count_file, 'w') as f:
                f.write(str(count))
        except Exception:
            pass
        return count


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


@app.route("/api/preview", methods=["POST"])
def preview():
    """
    Return 3D geometry data as JSON for the Three.js preview.
    This generates the staircase geometry as mesh data without creating an IFC file.
    """
    params = request.get_json()
    try:
        geometry = generate_preview_geometry(params)
        return jsonify({"success": True, "geometry": geometry})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/ifc_count", methods=["GET"])
def ifc_count():
    """Return the total number of IFC files generated."""
    return jsonify({"count": _get_ifc_count()})


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
        _increment_ifc_count()
        return send_file(
            filepath,
            as_attachment=True,
            download_name="staircase.ifc",
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
            download_name="staircase_plan.dxf",
            mimetype="application/dxf",
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
