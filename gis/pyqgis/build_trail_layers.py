"""
Build a QGIS project from TrailFeathers trail data.

Standalone PyQGIS script (no GUI). Run with the OSGeo4W Python:

    C:\\OSGeo4W\\bin\\python-qgis-ltr.bat gis\\pyqgis\\build_trail_layers.py

Outputs (in gis/data/):
    trailfeathers.gpkg   - layers: trails, trail_buffers, ebird_sightings (optional)
    trailfeathers.qgz    - QGIS project with styled layers + OpenStreetMap basemap

Optional: set EBIRD_API_KEY to fetch recent eBird observations near each trail.
"""
import json
import os
import sys
import urllib.request
import urllib.error

from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField, QgsFields, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsVectorFileWriter, QgsCategorizedSymbolRenderer,
    QgsRendererCategory, QgsMarkerSymbol, QgsFillSymbol,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
    QgsReferencedRectangle,
)
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtGui import QFont

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
GEOJSON = os.path.join(DATA, "trails.geojson")
GPKG = os.path.join(DATA, "trailfeathers.gpkg")
PROJECT = os.path.join(DATA, "trailfeathers.qgz")

BUFFER_METERS = 2000
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
WEBMERC = QgsCoordinateReferenceSystem("EPSG:3857")

DIFFICULTY_COLORS = {
    "Easiest": "#2ca25f",
    "Beginner": "#66c2a4",
    "Intermediate": "#fdae61",
    "Difficult": "#d7301f",
    "Unknown": "#999999",
}


def write_layer(layer, name, mode):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    opts.actionOnExistingFile = mode
    res = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, GPKG, QgsProject.instance().transformContext(), opts)
    if res[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError("Failed writing %s: %s" % (name, res))
    return QgsVectorLayer("%s|layername=%s" % (GPKG, name), name, "ogr")


def load_trails():
    lyr = QgsVectorLayer(GEOJSON, "trails_src", "ogr")
    if not lyr.isValid():
        sys.exit("Could not read %s. Run `node gis/export_trails.js` first." % GEOJSON)
    print("Loaded %d trails" % lyr.featureCount())
    return lyr


def build_buffers(trails):
    """Buffer each trail point by BUFFER_METERS, computed in Web Mercator."""
    fields = QgsFields()
    fields.append(QgsField("trail_id", QMetaType.Type.Int))
    fields.append(QgsField("name", QMetaType.Type.QString))
    fields.append(QgsField("radius_m", QMetaType.Type.Int))
    mem = QgsVectorLayer("Polygon?crs=EPSG:4326", "trail_buffers", "memory")
    mem.dataProvider().addAttributes(fields)
    mem.updateFields()

    fwd = QgsCoordinateTransform(WGS84, WEBMERC, QgsProject.instance())
    back = QgsCoordinateTransform(WEBMERC, WGS84, QgsProject.instance())
    feats = []
    for t in trails.getFeatures():
        g = QgsGeometry(t.geometry())
        g.transform(fwd)
        g = g.buffer(BUFFER_METERS, 32)
        g.transform(back)
        f = QgsFeature(fields)
        f.setGeometry(g)
        f.setAttributes([t["id"], t["name"], BUFFER_METERS])
        feats.append(f)
    mem.dataProvider().addFeatures(feats)
    return mem


def fetch_ebird(trails, api_key, dist_km=10, back_days=14):
    """Recent eBird observations near each trail -> point layer."""
    fields = QgsFields()
    for n, typ in [("trail_id", QMetaType.Type.Int), ("trail_name", QMetaType.Type.QString),
                   ("species_code", QMetaType.Type.QString), ("com_name", QMetaType.Type.QString),
                   ("sci_name", QMetaType.Type.QString), ("how_many", QMetaType.Type.Int),
                   ("obs_dt", QMetaType.Type.QString), ("loc_name", QMetaType.Type.QString)]:
        fields.append(QgsField(n, typ))
    mem = QgsVectorLayer("Point?crs=EPSG:4326", "ebird_sightings", "memory")
    mem.dataProvider().addAttributes(fields)
    mem.updateFields()

    feats = []
    for t in trails.getFeatures():
        p = t.geometry().asPoint()
        url = ("https://api.ebird.org/v2/data/obs/geo/recent"
               "?lat=%.4f&lng=%.4f&dist=%d&back=%d" % (p.y(), p.x(), dist_km, back_days))
        req = urllib.request.Request(url, headers={"X-eBirdApiToken": api_key})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                obs = json.load(r)
        except urllib.error.URLError as e:
            print("  eBird fetch failed for %s: %s" % (t["name"], e))
            continue
        for o in obs:
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(o["lng"], o["lat"])))
            f.setAttributes([t["id"], t["name"], o.get("speciesCode"), o.get("comName"),
                             o.get("sciName"), o.get("howMany"), o.get("obsDt"),
                             o.get("locName")])
            feats.append(f)
        print("  %s: %d observations" % (t["name"], len(obs)))
    mem.dataProvider().addFeatures(feats)
    return mem


def style_trails(layer):
    cats = []
    for diff, color in DIFFICULTY_COLORS.items():
        sym = QgsMarkerSymbol.createSimple({
            "name": "circle", "color": color, "outline_color": "#333333",
            "outline_width": "0.4", "size": "4"})
        cats.append(QgsRendererCategory(diff, sym, diff))
    layer.setRenderer(QgsCategorizedSymbolRenderer("difficulty", cats))

    lbl = QgsPalLayerSettings()
    lbl.fieldName = "name"
    lbl.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 9))
    fmt.setSize(9)
    lbl.setFormat(fmt)
    layer.setLabelsEnabled(True)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(lbl))


def style_buffers(layer):
    sym = QgsFillSymbol.createSimple({
        "color": "80,160,220,60", "outline_color": "#4a90d9", "outline_width": "0.3"})
    layer.renderer().setSymbol(sym)


def style_sightings(layer):
    sym = QgsMarkerSymbol.createSimple({
        "name": "triangle", "color": "#8e44ad", "outline_color": "#ffffff",
        "outline_width": "0.2", "size": "2.5"})
    layer.renderer().setSymbol(sym)


def main():
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        project = QgsProject.instance()
        project.setCrs(WEBMERC)

        src = load_trails()
        if os.path.exists(GPKG):
            os.remove(GPKG)
        trails = write_layer(src, "trails", QgsVectorFileWriter.CreateOrOverwriteFile)
        buffers = write_layer(build_buffers(src), "trail_buffers",
                              QgsVectorFileWriter.CreateOrOverwriteLayer)

        sightings = None
        key = os.environ.get("EBIRD_API_KEY")
        if key:
            print("Fetching eBird observations...")
            sightings = write_layer(fetch_ebird(src, key), "ebird_sightings",
                                    QgsVectorFileWriter.CreateOrOverwriteLayer)
        else:
            print("EBIRD_API_KEY not set; skipping eBird layer")

        osm = QgsRasterLayer(
            "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
            "OpenStreetMap", "wms")

        style_trails(trails)
        style_buffers(buffers)
        if sightings:
            style_sightings(sightings)

        for lyr in [osm, buffers] + ([sightings] if sightings else []) + [trails]:
            project.addMapLayer(lyr)

        project.setTitle("TrailFeathers")
        # Default view: trail extent (in project CRS) so the project opens on the map
        ext = trails.extent()
        ext = QgsCoordinateTransform(WGS84, WEBMERC, project).transformBoundingBox(ext)
        ext.grow(ext.width() * 0.1)
        project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext, WEBMERC))
        project.write(PROJECT)
        print("Wrote %s\nWrote %s" % (GPKG, PROJECT))

        print("\n%-40s %-14s %6s" % ("Trail", "Difficulty", "Miles"))
        for t in trails.getFeatures():
            print("%-40s %-14s %6s" % (t["name"][:40], t["difficulty"], t["length_mi"]))

        # Release layer references before shutting QGIS down; otherwise
        # teardown on Windows can access-violate after all work is done.
        project.removeAllMapLayers()
        del trails, buffers, sightings, osm, src
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    main()
