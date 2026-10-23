# TrailFeathers GIS (QGIS / PyQGIS)

Python tooling that turns the app's trail data into real GIS layers you can open, style and analyse in QGIS.

```
gis/
  export_trails.js                 Node: trails -> data/trails.geojson (dummy data or --db)
  pyqgis/build_trail_layers.py     Headless PyQGIS: GeoJSON -> GeoPackage + styled .qgz project
  qgis_plugin/trailfeathers/       QGIS plugin: load trails from the running server, eBird lookup
  data/                            generated outputs (trails.geojson, trailfeathers.gpkg, .qgz)
```

## 1. Export trail data

```
node gis/export_trails.js        # uses copyAPIparkData dummy trails, no DB required
node gis/export_trails.js --db   # pulls from MySQL through the Sequelize model
```

## 2. Build the QGIS project (headless)

Requires QGIS installed via OSGeo4W (tested with QGIS 3.40 LTR).

```
C:\OSGeo4W\bin\python-qgis-ltr.bat gis\pyqgis\build_trail_layers.py
```

Produces `gis/data/trailfeathers.gpkg` with layers:

| layer            | geometry | notes                                             |
|------------------|----------|---------------------------------------------------|
| trails           | Point    | categorized by `difficulty`, labelled by name     |
| trail_buffers    | Polygon  | 2 km buffer around each trailhead (Web Mercator)  |
| ebird_sightings  | Point    | only when `EBIRD_API_KEY` is set                  |

and `gis/data/trailfeathers.qgz`, a ready-to-open project on an OpenStreetMap basemap.

To include recent eBird observations (last 14 days, 10 km around each trail):

```
set EBIRD_API_KEY=your_token      # https://ebird.org/api/keygen
C:\OSGeo4W\bin\python-qgis-ltr.bat gis\pyqgis\build_trail_layers.py
```

## 3. QGIS plugin

Copy (or symlink) `gis/qgis_plugin/trailfeathers` into your QGIS plugin folder, e.g.

```
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\trailfeathers
```

then enable it in Plugins > Manage and Install Plugins. It adds three actions:

- **Load trails**: GET `/api/trails/geojson` from the running Express server (default `http://localhost:5555`), falling back to `gis/data/trails.geojson` if the server is down.
- **eBird near selected trail**: select one or more trail points, and the plugin adds a layer of recent eBird observations within 10 km.
- **Settings**: server URL and eBird API key.

## Server endpoint

`GET /api/trails/geojson` returns every row in the `trails` table as a GeoJSON FeatureCollection (added in `server/index.js`).

## Ideas for next steps

- Replace point trailheads with real trail linework (OpenStreetMap `highway=path` via QuickOSM, or the app's TrailAPI polylines).
- Sample a DEM (e.g. USGS 3DEP) along trails for elevation profiles and store `elevation_gain` on each trail.
- Spatial join eBird hotspots to trail buffers to rank trails by bird diversity, then expose that score through the API to the React front end.
- Run the builder on a schedule and serve the GeoPackage tiles back to the web app with `tipg` or `pg_tileserv`.
