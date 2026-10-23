"""
Add a gis/find_trails.py result to the TrailFeathers QGIS project and make it
the default view.

    C:\\OSGeo4W\\bin\\python-qgis-ltr.bat gis\\pyqgis\\add_place_layer.py gis\\data\\east_carroll_parish.geojson

Styling: named ways in red, unnamed tracks thin grey, parks/sites as green pins.
"""
import os
import sys

from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsReferencedRectangle, QgsRuleBasedRenderer,
    QgsLineSymbol, QgsMarkerSymbol, QgsFillSymbol, QgsSymbol, QgsWkbTypes,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
)
from qgis.PyQt.QtGui import QFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "..", "data", "trailfeathers.qgz")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
WEBMERC = QgsCoordinateReferenceSystem("EPSG:3857")


def rule_renderer(layer, geom):
    root = QgsRuleBasedRenderer.Rule(None)
    if geom == QgsWkbTypes.LineGeometry:
        rules = [
            ('"name" IS NOT NULL', "Named trail", QgsLineSymbol.createSimple(
                {"color": "#c0392b", "width": "1.2"})),
            ('"kind" IN (\'path\',\'footway\',\'cycleway\')', "Path / footway",
             QgsLineSymbol.createSimple({"color": "#e67e22", "width": "0.9"})),
            ("ELSE", "Track", QgsLineSymbol.createSimple(
                {"color": "#7f8c8d", "width": "0.35"})),
        ]
    elif geom == QgsWkbTypes.PointGeometry:
        rules = [("ELSE", "Park / site", QgsMarkerSymbol.createSimple(
            {"name": "diamond", "color": "#27ae60", "outline_color": "#145a32", "size": "3.5"}))]
    else:
        rules = [("ELSE", "Area", QgsFillSymbol.createSimple(
            {"color": "39,174,96,70", "outline_color": "#27ae60"}))]
    for expr, label, sym in rules:
        r = QgsRuleBasedRenderer.Rule(sym, label=label)
        if expr == "ELSE":
            r.setIsElse(True)
        else:
            r.setFilterExpression(expr)
        root.appendChild(r)
    layer.setRenderer(QgsRuleBasedRenderer(root))


def label(layer):
    s = QgsPalLayerSettings()
    s.fieldName = "name"
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 8))
    fmt.setSize(8)
    s.setFormat(fmt)
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
        for geom, suffix in [(QgsWkbTypes.PolygonGeometry, "areas"),
                             (QgsWkbTypes.LineGeometry, "trails"),
                             (QgsWkbTypes.PointGeometry, "sites")]:
            name = "%s_%s" % (base, suffix)
            for old in project.mapLayersByName(name):
                project.removeMapLayer(old.id())
            gtype = {QgsWkbTypes.PolygonGeometry: "Polygon", QgsWkbTypes.LineGeometry: "LineString",
                     QgsWkbTypes.PointGeometry: "Point"}[geom]
            lyr = QgsVectorLayer("%s|geometrytype=%s" % (geojson, gtype), name, "ogr")
            if not lyr.isValid() or lyr.featureCount() == 0:
                continue
            rule_renderer(lyr, geom)
            label(lyr)
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
