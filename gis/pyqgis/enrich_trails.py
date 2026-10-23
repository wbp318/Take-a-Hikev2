"""
Enrich TrailFeathers trails with real trail linework, elevation and a bird score.

Run after build_trail_layers.py, with the OSGeo4W Python:

    C:\\OSGeo4W\\bin\\python-qgis-ltr.bat gis\\pyqgis\\enrich_trails.py

For every trailhead point in gis/data/trails.geojson:

  1. OpenStreetMap linework  - all highway=path/footway/track/cycleway ways
                               within SEARCH_RADIUS_M (one Overpass request).
  2. Elevation profile       - vertices of those ways (thinned to ~100 m) are
                               sent to the Open-Meteo elevation API (90 m SRTM /
                               Copernicus DEM, free, no key). Gain/loss/min/max
                               are computed per trail from the longest segment.
  3. Bird diversity score    - eBird hotspots within 10 km with their all-time
                               species counts. Score = 0-100 scaled by species.
                               Requires EBIRD_API_KEY; otherwise left null.

Outputs:
  gis/data/trailfeathers.gpkg     +layers trail_lines, elevation_samples
  gis/data/trail_enrichment.json  {trail_id: {...}}  served by /api/trails/enrichment
"""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsVectorFileWriter, QgsDistanceArea,
    QgsCoordinateReferenceSystem, QgsLineSymbol, QgsMarkerSymbol,
)
from qgis.PyQt.QtCore import QMetaType

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
GEOJSON = os.path.join(DATA, "trails.geojson")
GPKG = os.path.join(DATA, "trailfeathers.gpkg")
OUT_JSON = os.path.join(DATA, "trail_enrichment.json")
PROJECT = os.path.join(DATA, "trailfeathers.qgz")
OSM_CACHE = os.path.join(DATA, "osm_lines_cache.json")

SEARCH_RADIUS_M = 3000
SAMPLE_SPACING_M = 100
MIRRORS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "trailfeathers-enrich/0.1 (github.com/wbp318/Take-a-Hikev2)"}

da = QgsDistanceArea()
da.setSourceCrs(QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance().transformContext())
da.setEllipsoid("WGS84")


# ----------------------------------------------------------------- HTTP helpers
def get_json(url, data=None, headers=None, timeout=180):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def overpass(query):
    """Query Overpass, falling back to the last successful response on disk."""
    for host in MIRRORS:
        try:
            data = get_json(host, urllib.parse.urlencode({"data": query}).encode())
            with open(OSM_CACHE, "w") as f:
                json.dump(data, f)
            return data
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print("  %s failed: %s" % (host, e))
            time.sleep(5)
    if os.path.exists(OSM_CACHE):
        print("  All Overpass mirrors failed; using cached %s" % OSM_CACHE)
        with open(OSM_CACHE) as f:
            return json.load(f)
    prev = QgsVectorLayer("%s|layername=trail_lines" % GPKG, "prev", "ogr")
    if prev.isValid() and prev.featureCount():
        print("  All Overpass mirrors failed; reusing trail_lines already in the GeoPackage")
        elements = []
        for f in prev.getFeatures():
            elements.append({
                "type": "way", "id": f["osm_id"],
                "tags": {k: f[k] for k in ("name", "highway", "surface") if f[k] is not None},
                "geometry": [{"lon": p.x(), "lat": p.y()} for p in f.geometry().asPolyline()],
            })
        return {"elements": elements}
    raise RuntimeError("All Overpass mirrors failed and no cache available")


def elevations(points):
    """points: list of (lon, lat). Open-Meteo accepts 100 per request."""
    out = []
    for i in range(0, len(points), 100):
        chunk = points[i:i + 100]
        q = urllib.parse.urlencode({
            "latitude": ",".join("%.5f" % p[1] for p in chunk),
            "longitude": ",".join("%.5f" % p[0] for p in chunk)})
        out += get_json("https://api.open-meteo.com/v1/elevation?" + q, timeout=60)["elevation"]
        time.sleep(0.3)
    return out


# ----------------------------------------------------------------- steps
def fetch_osm_lines(trails):
    clauses = "".join(
        '  way["highway"~"^(path|footway|track|cycleway|bridleway)$"](around:%d,%.5f,%.5f);\n'
        % (SEARCH_RADIUS_M, t.geometry().asPoint().y(), t.geometry().asPoint().x())
        for t in trails.getFeatures())
    q = "[out:json][timeout:170];\n(\n%s);\nout tags geom;" % clauses
    print("Querying Overpass for OSM linework near %d trails..." % trails.featureCount())
    return overpass(q).get("elements", [])


def nearest_trail(trails, line_geom):
    best, best_d = None, float("inf")
    for t in trails.getFeatures():
        d = line_geom.distance(t.geometry())  # degrees, fine for ranking
        if d < best_d:
            best, best_d = t, d
    return best


def build_lines_layer(trails, elements):
    fields = QgsFields()
    for n, t in [("osm_id", QMetaType.Type.LongLong), ("trail_id", QMetaType.Type.Int),
                 ("trail_name", QMetaType.Type.QString), ("name", QMetaType.Type.QString),
                 ("highway", QMetaType.Type.QString), ("surface", QMetaType.Type.QString),
                 ("length_m", QMetaType.Type.Double)]:
        fields.append(QgsField(n, t))
    lyr = QgsVectorLayer("LineString?crs=EPSG:4326", "trail_lines", "memory")
    lyr.dataProvider().addAttributes(fields)
    lyr.updateFields()

    feats, per_trail = [], {}
    for el in elements:
        if el["type"] != "way" or "geometry" not in el:
            continue
        pts = [QgsPointXY(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(pts) < 2:
            continue
        g = QgsGeometry.fromPolylineXY(pts)
        t = nearest_trail(trails, g)
        tags = el.get("tags", {})
        length = da.measureLength(g)
        f = QgsFeature(fields)
        f.setGeometry(g)
        f.setAttributes([el["id"], t["id"], t["name"], tags.get("name"), tags.get("highway"),
                         tags.get("surface"), round(length, 1)])
        feats.append(f)
        per_trail.setdefault(t["id"], []).append((length, g, tags.get("highway")))
    lyr.dataProvider().addFeatures(feats)
    print("  %d OSM ways matched" % len(feats))
    return lyr, per_trail


def thin(geom, spacing):
    """Return (lon, lat) samples every `spacing` metres along a line."""
    length = da.measureLength(geom)
    n = max(2, int(length // spacing) + 1)
    total_deg = geom.length()
    pts = []
    for i in range(n):
        p = geom.interpolate(total_deg * i / (n - 1)).asPoint()
        pts.append((p.x(), p.y()))
    return pts


def elevation_stats(trails, per_trail):
    fields = QgsFields()
    for n, t in [("trail_id", QMetaType.Type.Int), ("seq", QMetaType.Type.Int),
                 ("dist_m", QMetaType.Type.Double), ("elev_m", QMetaType.Type.Double)]:
        fields.append(QgsField(n, t))
    lyr = QgsVectorLayer("Point?crs=EPSG:4326", "elevation_samples", "memory")
    lyr.dataProvider().addAttributes(fields)
    lyr.updateFields()

    stats, feats = {}, []
    print("Sampling elevation...")
    for t in trails.getFeatures():
        tid = t["id"]
        head = t.geometry().asPoint()
        segs = per_trail.get(tid, [])
        if segs:
            length, g, _ = max(segs, key=lambda s: s[0])
            pts = thin(g, SAMPLE_SPACING_M)
        else:
            length, pts = 0, [(head.x(), head.y())]
        el = elevations(pts)
        gain = sum(max(0, el[i + 1] - el[i]) for i in range(len(el) - 1))
        loss = sum(max(0, el[i] - el[i + 1]) for i in range(len(el) - 1))
        stats[tid] = {
            "trailhead_elev_m": elevations([(head.x(), head.y())])[0],
            "elev_min_m": min(el), "elev_max_m": max(el),
            "elev_gain_m": round(gain, 1), "elev_loss_m": round(loss, 1),
            "profile_segment_m": round(length, 1), "profile_samples": len(el),
        }
        step = length / max(1, len(pts) - 1)
        for i, ((x, y), z) in enumerate(zip(pts, el)):
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([tid, i, round(i * step, 1), z])
            feats.append(f)
        print("  %-36s gain %5.0f m over %6.0f m (%d samples)" % (t["name"][:36], gain, length, len(el)))
    lyr.dataProvider().addFeatures(feats)
    return lyr, stats


def bird_scores(trails, key):
    scores = {}
    if not key:
        print("EBIRD_API_KEY not set; bird scores left null")
        return {t["id"]: {"bird_hotspots": None, "bird_species_max": None, "bird_score": None}
                for t in trails.getFeatures()}
    print("Fetching eBird hotspots...")
    raw = {}
    for t in trails.getFeatures():
        p = t.geometry().asPoint()
        url = ("https://api.ebird.org/v2/ref/hotspot/geo?lat=%.4f&lng=%.4f&dist=10&fmt=json"
               % (p.y(), p.x()))
        try:
            hs = get_json(url, headers={"X-eBirdApiToken": key}, timeout=30)
        except urllib.error.URLError as e:
            print("  %s: %s" % (t["name"], e))
            hs = []
        counts = [h.get("numSpeciesAllTime") or 0 for h in hs]
        raw[t["id"]] = (len(hs), max(counts) if counts else 0, sum(counts))
        time.sleep(0.2)
    top = max((v[1] for v in raw.values()), default=1) or 1
    for tid, (n, mx, total) in raw.items():
        scores[tid] = {"bird_hotspots": n, "bird_species_max": mx,
                       "bird_score": round(100 * mx / top)}
    return scores


def write_layer(layer, name):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    res = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, GPKG, QgsProject.instance().transformContext(), opts)
    if res[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError("Failed writing %s: %s" % (name, res))


def main():
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        if not os.path.exists(GPKG):
            sys.exit("Run build_trail_layers.py first")
        trails = QgsVectorLayer(GEOJSON, "trails", "ogr")
        if not trails.isValid():
            sys.exit("Could not read " + GEOJSON)

        lines, per_trail = build_lines_layer(trails, fetch_osm_lines(trails))
        samples, elev = elevation_stats(trails, per_trail)
        birds = bird_scores(trails, os.environ.get("EBIRD_API_KEY"))

        write_layer(lines, "trail_lines")
        write_layer(samples, "elevation_samples")

        enrichment = {}
        for t in trails.getFeatures():
            tid = t["id"]
            segs = per_trail.get(tid, [])
            enrichment[str(tid)] = {
                "name": t["name"],
                "osm_segments": len(segs),
                "osm_length_km": round(sum(s[0] for s in segs) / 1000, 2),
                "osm_surface_types": sorted({s[2] for s in segs if s[2]}),
                **elev[tid], **birds[tid],
            }
        with open(OUT_JSON, "w") as f:
            json.dump(enrichment, f, indent=2)
        print("Wrote %s\nWrote layers trail_lines, elevation_samples to %s" % (OUT_JSON, GPKG))

        # Add the new layers to the QGIS project written by build_trail_layers.py
        if os.path.exists(PROJECT):
            project = QgsProject.instance()
            project.read(PROJECT)
            for name in ("trail_lines", "elevation_samples"):
                for old in project.mapLayersByName(name):
                    project.removeMapLayer(old.id())
            ll = QgsVectorLayer("%s|layername=trail_lines" % GPKG, "trail_lines", "ogr")
            ll.renderer().setSymbol(QgsLineSymbol.createSimple(
                {"color": "#c0392b", "width": "0.8", "line_style": "dash"}))
            es = QgsVectorLayer("%s|layername=elevation_samples" % GPKG, "elevation_samples", "ogr")
            es.renderer().setSymbol(QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": "#2c3e50", "size": "1", "outline_style": "no"}))
            project.addMapLayer(es)
            project.addMapLayer(ll)
            project.write(PROJECT)
            project.removeAllMapLayers()
            print("Updated %s" % PROJECT)
            del ll, es

        del trails, lines, samples
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    main()
