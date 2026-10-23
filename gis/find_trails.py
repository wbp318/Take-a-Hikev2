"""
Find hiking / walking trails, parks and nature areas in a US county or parish
using OpenStreetMap (Overpass API). Plain Python, no QGIS required.

    python gis/find_trails.py "East Carroll Parish" --state Louisiana
    python gis/find_trails.py "East Carroll Parish" --out gis/data/east_carroll.geojson

Writes a GeoJSON FeatureCollection (lines for ways, points for parks/sites)
and prints a summary table. Output opens directly in QGIS and can be fed to
gis/pyqgis/build_trail_layers.py by pointing GEOJSON at it.
"""
import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "trailfeathers-find-trails/0.1 (github.com/wbp318/Take-a-Hikev2)"}

TRAIL_HIGHWAYS = "path|footway|track|cycleway|bridleway|steps"


def geocode_bbox(name, state):
    q = urllib.parse.urlencode({"q": f"{name}, {state}, USA", "format": "json", "limit": 1,
                                "polygon_geojson": 0})
    with urllib.request.urlopen(urllib.request.Request(f"{NOMINATIM}?{q}", headers=UA),
                                timeout=30) as r:
        res = json.load(r)
    if not res:
        sys.exit(f"Could not geocode {name}, {state}")
    s, n, w, e = map(float, res[0]["boundingbox"])
    return s, w, n, e, res[0]["display_name"]


def overpass(query):
    last = None
    for host in MIRRORS:
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    host, data=urllib.parse.urlencode({"data": query}).encode(), headers=UA)
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
                print(f"  {host}: {e}; retrying", file=sys.stderr)
                time.sleep(10)
    sys.exit(f"All Overpass mirrors failed: {last}")


def haversine_m(a, b):
    R = 6371000
    la1, lo1, la2, lo2 = map(math.radians, [a[1], a[0], b[1], b[0]])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def build_query(bbox, include_tracks):
    s, w, n, e = bbox
    bb = f"({s},{w},{n},{e})"
    hw = TRAIL_HIGHWAYS if include_tracks else TRAIL_HIGHWAYS.replace("track|", "")
    return f"""[out:json][timeout:170];
(
  way["highway"~"^({hw})$"]{bb};
  way["route"="hiking"]{bb};
  relation["route"~"^(hiking|foot|bicycle)$"]{bb};
  nwr["leisure"~"^(park|nature_reserve|garden)$"]{bb};
  nwr["boundary"~"^(national_park|protected_area)$"]{bb};
  nwr["tourism"~"^(camp_site|picnic_site|viewpoint|wilderness_hut)$"]{bb};
  nwr["natural"~"^(wood|wetland|beach)$"]["name"]{bb};
);
out tags geom;"""


def to_features(elements):
    feats = []
    for el in elements:
        t = el.get("tags", {})
        kind = (t.get("highway") or t.get("route") or t.get("leisure") or t.get("boundary")
                or t.get("tourism") or t.get("natural") or "other")
        props = {
            "osm_type": el["type"], "osm_id": el["id"], "name": t.get("name"),
            "kind": kind, "surface": t.get("surface"), "sac_scale": t.get("sac_scale"),
            "access": t.get("access"), "operator": t.get("operator"),
            "osm_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        }
        geom = None
        if el["type"] == "way" and "geometry" in el:
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            length = sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))
            props["length_km"] = round(length / 1000, 2)
            closed = coords[0] == coords[-1] and len(coords) > 3
            is_area = closed and kind not in TRAIL_HIGHWAYS.split("|")
            geom = {"type": "Polygon", "coordinates": [coords]} if is_area else \
                   {"type": "LineString", "coordinates": coords}
        elif el["type"] == "node":
            geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
        elif el["type"] == "relation":
            lines = [[[p["lon"], p["lat"]] for p in m["geometry"]]
                     for m in el.get("members", []) if m.get("geometry")]
            if lines:
                total = sum(haversine_m(l[i], l[i + 1]) for l in lines for i in range(len(l) - 1))
                props["length_km"] = round(total / 1000, 2)
                geom = {"type": "MultiLineString", "coordinates": lines}
        if geom:
            feats.append({"type": "Feature", "geometry": geom, "properties": props})
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("place", help='e.g. "East Carroll Parish"')
    ap.add_argument("--state", default="Louisiana")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-tracks", action="store_true",
                    help="exclude highway=track (farm/levee roads); on by default in rural areas")
    args = ap.parse_args()

    s, w, n, e, label = geocode_bbox(args.place, args.state)
    print(f"Searching {label}\n  bbox S{s:.3f} W{w:.3f} N{n:.3f} E{e:.3f}")
    data = overpass(build_query((s, w, n, e), not args.no_tracks))
    feats = to_features(data.get("elements", []))

    out = args.out or f"gis/data/{args.place.lower().replace(' ', '_')}.geojson"
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)

    named = [f for f in feats if f["properties"]["name"]]
    unnamed_by_kind = {}
    for f in feats:
        if not f["properties"]["name"]:
            k = f["properties"]["kind"]
            unnamed_by_kind[k] = unnamed_by_kind.get(k, 0) + 1

    print(f"\n{len(feats)} features written to {out}\n")
    print(f"{'Name':<48} {'Kind':<16} {'km':>6}  OSM")
    for f in sorted(named, key=lambda f: (f["properties"]["kind"], f["properties"]["name"])):
        p = f["properties"]
        print(f"{p['name'][:48]:<48} {p['kind']:<16} {str(p.get('length_km', '')):>6}  {p['osm_url']}")
    if unnamed_by_kind:
        print("\nUnnamed features:", ", ".join(f"{k}: {v}" for k, v in sorted(unnamed_by_kind.items())))


if __name__ == "__main__":
    main()
