"""
DXF Plan View Generator — generates a minimal DXF R2010 file.

Pure Python, no external dependencies (no ezdxf needed).
Generates raw DXF text directly so it works in Pyodide without issues.

Public entry point:
    meshes_to_dxf(meshes, params) -> str   # returns path to temp DXF file
"""

import os
import tempfile


class DxfWriter:
    """Minimal DXF R2010 text generator for 2D plan-view drawings."""

    def __init__(self):
        self._handle = 100  # entity handle counter (hex)
        self._linetypes = []
        self._layers = []
        self._entities = []

    def _next_handle(self):
        h = format(self._handle, 'X')
        self._handle += 1
        return h

    def define_linetype(self, name, description, pattern):
        """Define a linetype. pattern is list of floats (positive=dash, negative=gap)."""
        self._linetypes.append((name, description, pattern))

    def define_layer(self, name, color=7, linetype="Continuous"):
        """Define a layer with colour and default linetype."""
        self._layers.append((name, color, linetype))

    def add_line(self, x1, y1, x2, y2, layer="0", color=None, linetype=None):
        """Add a LINE entity at Z=0."""
        self._entities.append(('LINE', {
            'layer': layer,
            'color': color,
            'linetype': linetype,
            'x1': x1, 'y1': y1,
            'x2': x2, 'y2': y2,
        }))

    def add_lwpolyline(self, points, closed=False, layer="0", color=None, linetype=None):
        """Add an LWPOLYLINE entity at Z=0. points is list of (x, y) tuples."""
        self._entities.append(('LWPOLYLINE', {
            'layer': layer,
            'color': color,
            'linetype': linetype,
            'points': points,
            'closed': closed,
        }))

    def save(self, filepath):
        """Assemble the full DXF file and write to filepath."""
        lines = []
        lines.extend(self._build_header())
        lines.extend(self._build_classes())
        lines.extend(self._build_tables())
        lines.extend(self._build_blocks())
        lines.extend(self._build_entities())
        lines.extend(self._build_objects())
        lines.append('  0')
        lines.append('EOF')
        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))

    def _build_header(self):
        lines = []
        lines.append('  0')
        lines.append('SECTION')
        lines.append('  2')
        lines.append('HEADER')
        # DXF version: AC1024 = R2010
        lines.extend(self._var('$ACADVER', 1, 'AC1024'))
        # Units: 4 = millimetres
        lines.extend(self._var('$INSUNITS', 70, 4))
        # Metric measurement
        lines.extend(self._var('$MEASUREMENT', 70, 1))
        lines.append('  0')
        lines.append('ENDSEC')
        return lines

    def _var(self, name, group, value):
        return ['  9', name, f'  {group}', str(value)]

    def _build_classes(self):
        return ['  0', 'SECTION', '  2', 'CLASSES', '  0', 'ENDSEC']

    def _build_tables(self):
        lines = []
        lines.append('  0')
        lines.append('SECTION')
        lines.append('  2')
        lines.append('TABLES')

        # VPORT table (required, minimal)
        lines.extend(self._table_wrapper('VPORT', self._vport_entries()))
        # LTYPE table
        lines.extend(self._table_wrapper('LTYPE', self._ltype_entries()))
        # LAYER table
        lines.extend(self._table_wrapper('LAYER', self._layer_entries()))
        # STYLE table (required, minimal)
        lines.extend(self._table_wrapper('STYLE', []))
        # VIEW table
        lines.extend(self._table_wrapper('VIEW', []))
        # UCS table
        lines.extend(self._table_wrapper('UCS', []))
        # APPID table
        lines.extend(self._table_wrapper('APPID', self._appid_entries()))
        # DIMSTYLE table
        lines.extend(self._table_wrapper('DIMSTYLE', []))
        # BLOCK_RECORD table
        lines.extend(self._table_wrapper('BLOCK_RECORD', self._block_record_entries()))

        lines.append('  0')
        lines.append('ENDSEC')
        return lines

    def _table_wrapper(self, name, entries):
        lines = []
        lines.append('  0')
        lines.append('TABLE')
        lines.append('  2')
        lines.append(name)
        lines.append('  5')
        lines.append(self._next_handle())
        lines.append('100')
        lines.append('AcDbSymbolTable')
        lines.append(' 70')
        lines.append(str(len(entries)))
        for entry in entries:
            lines.extend(entry)
        lines.append('  0')
        lines.append('ENDTAB')
        return lines

    def _vport_entries(self):
        entry = []
        entry.append('  0')
        entry.append('VPORT')
        entry.append('  5')
        entry.append(self._next_handle())
        entry.append('100')
        entry.append('AcDbSymbolTableRecord')
        entry.append('100')
        entry.append('AcDbViewportTableRecord')
        entry.append('  2')
        entry.append('*Active')
        entry.append(' 70')
        entry.append('0')
        # View centre
        entry.append(' 10')
        entry.append('0.0')
        entry.append(' 20')
        entry.append('0.0')
        # View height
        entry.append(' 40')
        entry.append('3000.0')
        return [entry]

    def _ltype_entries(self):
        entries = []
        # ByBlock
        entries.append(self._ltype_entry('ByBlock', '', []))
        # ByLayer
        entries.append(self._ltype_entry('ByLayer', '', []))
        # Continuous
        entries.append(self._ltype_entry('Continuous', 'Solid line', []))
        # User-defined linetypes
        for name, desc, pattern in self._linetypes:
            entries.append(self._ltype_entry(name, desc, pattern))
        return entries

    def _ltype_entry(self, name, description, pattern):
        entry = []
        entry.append('  0')
        entry.append('LTYPE')
        entry.append('  5')
        entry.append(self._next_handle())
        entry.append('100')
        entry.append('AcDbSymbolTableRecord')
        entry.append('100')
        entry.append('AcDbLinetypeTableRecord')
        entry.append('  2')
        entry.append(name)
        entry.append(' 70')
        entry.append('0')
        entry.append('  3')
        entry.append(description)
        entry.append(' 72')
        entry.append('65')  # alignment code 'A'
        entry.append(' 73')
        entry.append(str(len(pattern)))
        # Total pattern length
        total = sum(abs(v) for v in pattern)
        entry.append(' 40')
        entry.append(f'{total:.6f}')
        for val in pattern:
            entry.append(' 49')
            entry.append(f'{val:.6f}')
            entry.append(' 74')
            entry.append('0')
        return entry

    def _layer_entries(self):
        entries = []
        # Layer "0" (default)
        entries.append(self._layer_entry('0', 7, 'Continuous'))
        for name, color, linetype in self._layers:
            entries.append(self._layer_entry(name, color, linetype))
        return entries

    def _layer_entry(self, name, color, linetype):
        entry = []
        entry.append('  0')
        entry.append('LAYER')
        entry.append('  5')
        entry.append(self._next_handle())
        entry.append('100')
        entry.append('AcDbSymbolTableRecord')
        entry.append('100')
        entry.append('AcDbLayerTableRecord')
        entry.append('  2')
        entry.append(name)
        entry.append(' 70')
        entry.append('0')
        entry.append(' 62')
        entry.append(str(color))
        entry.append('  6')
        entry.append(linetype)
        return entry

    def _appid_entries(self):
        entry = []
        entry.append('  0')
        entry.append('APPID')
        entry.append('  5')
        entry.append(self._next_handle())
        entry.append('100')
        entry.append('AcDbSymbolTableRecord')
        entry.append('100')
        entry.append('AcDbRegAppTableRecord')
        entry.append('  2')
        entry.append('ACAD')
        entry.append(' 70')
        entry.append('0')
        return [entry]

    def _block_record_entries(self):
        entries = []
        for name in ('*Model_Space', '*Paper_Space'):
            entry = []
            entry.append('  0')
            entry.append('BLOCK_RECORD')
            entry.append('  5')
            entry.append(self._next_handle())
            entry.append('100')
            entry.append('AcDbSymbolTableRecord')
            entry.append('100')
            entry.append('AcDbBlockRecordTableRecord')
            entry.append('  2')
            entry.append(name)
            entries.append(entry)
        return entries

    def _build_blocks(self):
        lines = []
        lines.append('  0')
        lines.append('SECTION')
        lines.append('  2')
        lines.append('BLOCKS')
        for name in ('*Model_Space', '*Paper_Space'):
            lines.append('  0')
            lines.append('BLOCK')
            lines.append('  5')
            lines.append(self._next_handle())
            lines.append('100')
            lines.append('AcDbEntity')
            lines.append('  8')
            lines.append('0')
            lines.append('100')
            lines.append('AcDbBlockBegin')
            lines.append('  2')
            lines.append(name)
            lines.append(' 70')
            lines.append('0')
            lines.append(' 10')
            lines.append('0.0')
            lines.append(' 20')
            lines.append('0.0')
            lines.append(' 30')
            lines.append('0.0')
            lines.append('  0')
            lines.append('ENDBLK')
            lines.append('  5')
            lines.append(self._next_handle())
            lines.append('100')
            lines.append('AcDbEntity')
            lines.append('  8')
            lines.append('0')
            lines.append('100')
            lines.append('AcDbBlockEnd')
        lines.append('  0')
        lines.append('ENDSEC')
        return lines

    def _build_entities(self):
        lines = []
        lines.append('  0')
        lines.append('SECTION')
        lines.append('  2')
        lines.append('ENTITIES')
        for etype, props in self._entities:
            if etype == 'LINE':
                lines.extend(self._emit_line(props))
            elif etype == 'LWPOLYLINE':
                lines.extend(self._emit_lwpolyline(props))
        lines.append('  0')
        lines.append('ENDSEC')
        return lines

    def _emit_common(self, props):
        """Emit common entity properties: handle, layer, colour, linetype."""
        lines = []
        lines.append('  5')
        lines.append(self._next_handle())
        lines.append('100')
        lines.append('AcDbEntity')
        lines.append('  8')
        lines.append(props.get('layer', '0'))
        if props.get('color') is not None:
            lines.append(' 62')
            lines.append(str(props['color']))
        if props.get('linetype'):
            lines.append('  6')
            lines.append(props['linetype'])
        return lines

    def _emit_line(self, props):
        lines = []
        lines.append('  0')
        lines.append('LINE')
        lines.extend(self._emit_common(props))
        lines.append('100')
        lines.append('AcDbLine')
        lines.append(' 10')
        lines.append(f'{props["x1"]:.6f}')
        lines.append(' 20')
        lines.append(f'{props["y1"]:.6f}')
        lines.append(' 30')
        lines.append('0.0')
        lines.append(' 11')
        lines.append(f'{props["x2"]:.6f}')
        lines.append(' 21')
        lines.append(f'{props["y2"]:.6f}')
        lines.append(' 31')
        lines.append('0.0')
        return lines

    def _emit_lwpolyline(self, props):
        pts = props['points']
        lines = []
        lines.append('  0')
        lines.append('LWPOLYLINE')
        lines.extend(self._emit_common(props))
        lines.append('100')
        lines.append('AcDbPolyline')
        lines.append(' 90')
        lines.append(str(len(pts)))
        lines.append(' 70')
        lines.append('1' if props.get('closed') else '0')
        lines.append(' 43')
        lines.append('0.0')
        for x, y in pts:
            lines.append(' 10')
            lines.append(f'{x:.6f}')
            lines.append(' 20')
            lines.append(f'{y:.6f}')
        return lines

    def _build_objects(self):
        lines = []
        lines.append('  0')
        lines.append('SECTION')
        lines.append('  2')
        lines.append('OBJECTS')
        # Minimal DICTIONARY root object
        lines.append('  0')
        lines.append('DICTIONARY')
        lines.append('  5')
        lines.append(self._next_handle())
        lines.append('100')
        lines.append('AcDbDictionary')
        lines.append('281')
        lines.append('1')
        lines.append('  0')
        lines.append('ENDSEC')
        return lines


def meshes_to_dxf(meshes, params):
    """Generate a minimal DXF plan-view file.

    Args:
        meshes: list of mesh dicts from generate_preview_geometry()
        params: raw parameter dict from the UI

    Returns:
        str: path to temporary DXF file
    """
    dxf = DxfWriter()

    # Define DASHED linetype
    dxf.define_linetype('DASHED', 'Dashed line', [6.35, -3.175])

    # Define layers
    dxf.define_layer('STAIR_TREADS', color=0, linetype='Continuous')
    dxf.define_layer('STAIR_RISERS', color=9, linetype='DASHED')
    dxf.define_layer('STAIR_STRINGERS', color=0, linetype='Continuous')
    dxf.define_layer('STAIR_HANDRAIL', color=0, linetype='Continuous')

    # For now: draw a simple cross at origin so the file isn't empty
    # and we can confirm the download pipeline works
    dxf.add_line(-100, 0, 100, 0, layer='STAIR_TREADS', color=0)
    dxf.add_line(0, -100, 0, 100, layer='STAIR_TREADS', color=0)

    # Write to temp file
    fd, filepath = tempfile.mkstemp(suffix='.dxf')
    os.close(fd)
    dxf.save(filepath)
    return filepath
