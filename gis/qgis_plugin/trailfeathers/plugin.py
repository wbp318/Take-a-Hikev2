"""
TrailFeathers QGIS plugin.

Two actions in the Plugins menu / toolbar:
  * Load trails        - GET http://localhost:5555/api/trails/geojson (or a local
                         gis/data/trails.geojson fallback) and add a styled layer.
  * eBird near trail   - for the selected trail feature, fetch recent eBird
                         observations within 10 km and add them as a point layer.

Settings (stored in QGIS settings under trailfeathers/):
  server_url   default http://localhost:5555
  ebird_key    eBird API token (https://ebird.org/api/keygen)
"""
import json
import os
import urllib.request
import urllib.error

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField,
    QgsFields, QgsSettings, QgsCategorizedSymbolRenderer, QgsRendererCategory,
    QgsMarkerSymbol, Qgis,
)
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import QAction, QInputDialog, QLineEdit

DIFFICULTY_COLORS = {
    "Easiest": "#2ca25f", "Beginner": "#66c2a4", "Intermediate": "#fdae61",
    "Difficult": "#d7301f", "Unknown": "#999999",
}
LOCAL_GEOJSON = os.path.join(os.path.dirname(__file__), "..", "..", "data", "trails.geojson")


class TrailFeathersPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []

    # ---- plugin lifecycle -------------------------------------------------
    def initGui(self):
        for text, cb in [("TrailFeathers: Load trails", self.load_trails),
                         ("TrailFeathers: eBird near selected trail", self.ebird_near_trail),
                         ("TrailFeathers: Settings", self.settings)]:
            a = QAction(text, self.iface.mainWindow())
            a.triggered.connect(cb)
            self.iface.addPluginToMenu("&TrailFeathers", a)
            self.iface.addToolBarIcon(a)
            self.actions.append(a)

    def unload(self):
        for a in self.actions:
            self.iface.removePluginMenu("&TrailFeathers", a)
            self.iface.removeToolBarIcon(a)

    # ---- helpers ----------------------------------------------------------
    def _setting(self, key, default=""):
        return QgsSettings().value("trailfeathers/" + key, default)

    def _msg(self, text, level=Qgis.Info):
        self.iface.messageBar().pushMessage("TrailFeathers", text, level=level, duration=6)

    def _get_json(self, url, headers=None):
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    # ---- actions ----------------------------------------------------------
    def settings(self):
        s = QgsSettings()
        url, ok = QInputDialog.getText(None, "TrailFeathers", "Server URL",
                                       text=self._setting("server_url", "http://localhost:5555"))
        if ok:
            s.setValue("trailfeathers/server_url", url.rstrip("/"))
        key, ok = QInputDialog.getText(None, "TrailFeathers", "eBird API key",
                                       QLineEdit.Password, self._setting("ebird_key"))
        if ok:
            s.setValue("trailfeathers/ebird_key", key)

    def load_trails(self):
        url = self._setting("server_url", "http://localhost:5555") + "/api/trails/geojson"
        try:
            fc = self._get_json(url)
            src = "memory"
        except (urllib.error.URLError, ValueError):
            if not os.path.exists(LOCAL_GEOJSON):
                self._msg("Server unreachable and no local trails.geojson", Qgis.Critical)
                return
            with open(LOCAL_GEOJSON) as f:
                fc = json.load(f)
            src = "local file"

        layer = QgsVectorLayer(json.dumps(fc), "trails", "ogr")
        if not layer.isValid():
            self._msg("Trail data is not valid GeoJSON", Qgis.Critical)
            return

        cats = []
        for diff, color in DIFFICULTY_COLORS.items():
            sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": color,
                                                "outline_color": "#333", "size": "4"})
            cats.append(QgsRendererCategory(diff, sym, diff))
        layer.setRenderer(QgsCategorizedSymbolRenderer("difficulty", cats))
        QgsProject.instance().addMapLayer(layer)
        self.iface.mapCanvas().setExtent(layer.extent())
        self._msg("Loaded %d trails from %s" % (layer.featureCount(), src))

    def ebird_near_trail(self):
        key = self._setting("ebird_key")
        if not key:
            self._msg("Set an eBird API key in TrailFeathers: Settings", Qgis.Warning)
            return
        layer = self.iface.activeLayer()
        if layer is None or layer.selectedFeatureCount() == 0:
            self._msg("Select a trail feature in the trails layer first", Qgis.Warning)
            return

        fields = QgsFields()
        for n, t in [("trail_name", QMetaType.Type.QString), ("com_name", QMetaType.Type.QString),
                     ("sci_name", QMetaType.Type.QString), ("how_many", QMetaType.Type.Int),
                     ("obs_dt", QMetaType.Type.QString), ("loc_name", QMetaType.Type.QString)]:
            fields.append(QgsField(n, t))
        out = QgsVectorLayer("Point?crs=EPSG:4326", "ebird_sightings", "memory")
        out.dataProvider().addAttributes(fields)
        out.updateFields()

        feats = []
        for trail in layer.selectedFeatures():
            p = trail.geometry().asPoint()
            url = ("https://api.ebird.org/v2/data/obs/geo/recent"
                   "?lat=%.4f&lng=%.4f&dist=10&back=14" % (p.y(), p.x()))
            try:
                obs = self._get_json(url, {"X-eBirdApiToken": key})
            except urllib.error.URLError as e:
                self._msg("eBird request failed: %s" % e, Qgis.Critical)
                return
            name = trail["name"] if "name" in trail.fields().names() else ""
            for o in obs:
                f = QgsFeature(fields)
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(o["lng"], o["lat"])))
                f.setAttributes([name, o.get("comName"), o.get("sciName"),
                                 o.get("howMany"), o.get("obsDt"), o.get("locName")])
                feats.append(f)

        out.dataProvider().addFeatures(feats)
        out.renderer().setSymbol(QgsMarkerSymbol.createSimple(
            {"name": "triangle", "color": "#8e44ad", "outline_color": "#fff", "size": "2.5"}))
        QgsProject.instance().addMapLayer(out)
        self._msg("Added %d eBird observations" % len(feats))
