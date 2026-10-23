"""
Add a gis/find_trails.py result to the TrailFeathers QGIS project and make it
the default view.

    C:\\OSGeo4W\\bin\\python-qgis-ltr.bat gis\\pyqgis\\add_place_layer.py gis\\data\\east_carroll_parish.geojson

Layers added: <place>_named_trails (red, labelled along the line),
<place>_paths (unnamed paths/footways, orange), <place>_tracks (grey),
<place>_sites (green diamonds), <place>_areas (polygons).
"""
import os
import sys

from qgis.core import (
    Qgis, QgsApplication, QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsReferencedRectangle, QgsLineSymbol, QgsMarkerSymbol, QgsFillSymbol,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
)
from qgis.PyQt.QtGui import QFont, QColor

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "..", "data", "trailfeathers.qgz")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
WEBMERC = QgsCoordinateReferenceSystem("EPSG:3857")


def label(layer, along_line=False):
    s = QgsPalLayerSettings()
    s.fieldName = "name"
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 9))
    fmt.setSize(9)
    fmt.setColor(QColor("#7b241c") if along_line else QColor("#145a32"))
    buf = fmt.buffer()
    buf.setEnabled(True)
    buf.setSize(1)
    buf.setColor(QColor("white"))
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    if along_line:
        s.placement = Qgis.LabelPlacement.Line
        s.lineSettings().setMergeLines(True)
        s.priority = 10
    layer.setLabelsEnabled(True)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))


def main(geojson):
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        project = QgsProject.instance()
        project.read(PROJECT)
        base = os.path.splitext(os.path.basename(geojson))[0]
        added = []
        specs = [
            ("areas", "Polygon", None, QgsFillSymbol.createSimple(
                {"color": "39,174,96,70", "outline_color": "#27ae60"}), True),
            ("tracks", "LineString", "\"name\" IS NULL AND \"kind\" = 'track'",
             QgsLineSymbol.createSimple({"color": "#7f8c8d", "width": "0.35"}), False),
            ("paths", "LineString", "\"name\" IS NULL AND \"kind\" <> 'track'",
             QgsLineSymbol.createSimple({"color": "#e67e22", "width": "0.9"}), False),
            ("named_trails", "LineString", '"name" IS NOT NULL',
             QgsLineSymbol.createSimple({"color": "#c0392b", "width": "1.2"}), True),
            ("sites", "Point", None, QgsMarkerSymbol.createSimple(
                {"name": "diamond", "color": "#27ae60", "outline_color": "#145a32", "size": "3.5"}), True),
        ]
        for old_suffix in ("trails",):
            for old in project.mapLayersByName("%s_%s" % (base, old_suffix)):
                project.removeMapLayer(old.id())
        for suffix, gtype, flt, sym, labelled in specs:
            name = "%s_%s" % (base, suffix)
            for old in project.mapLayersByName(name):
                project.removeMapLayer(old.id())
            lyr = QgsVectorLayer("%s|geometrytype=%s" % (geojson, gtype), name, "ogr")
            if not lyr.isValid():
                continue
            if flt:
                lyr.setSubsetString(flt)
            if lyr.featureCount() == 0:
                continue
            lyr.renderer().setSymbol(sym)
            if labelled:
                label(lyr, along_line=(gtype == "LineString"))
            project.addMapLayer(lyr)
            added.append(lyr)
            print("Added %s (%d features)" % (name, lyr.featureCount()))

        ext = None
        for lyr in added:
            ext = lyr.extent() if ext is None else ext.combineExtentWith(lyr.extent()) or ext
        ext = QgsCoordinateTransform(WGS84, WEBMERC, project).transformBoundingBox(ext)
        ext.grow(ext.width() * 0.05)
        project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext, WEBMERC))
        project.write(PROJECT)
        print("Project view set to %s" % base)
        project.removeAllMapLayers()
        del added, lyr
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
