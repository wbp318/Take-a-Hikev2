# TrailFeathers GIS (QGIS / PyQGIS)

Python tooling that turns the app's trail data into real GIS layers you can open, style and analyse in QGIS.

```
gis/
  export_trails.js                 Node: trails -> data/trails.geojson (dummy data or --db)
  pyqgis/build_trail_layers.py     Headless PyQGIS: GeoJSON -> GeoPackage + styled .qgz project
  qgis_plugin/trailfeathers/       QGIS plugin: load trails from the running server, eBird lookup
  data/                            generated outputs (trails.geojson, trailfeathers.gpkg, .qgz)
```

## How it fits together

```mermaid
flowchart LR
    subgraph app["TrailFeathers app (Node / React)"]
        DB[(MySQL<br/>trails table)]
        DUMMY[copyAPIparkData<br/>dummy trails]
        API_GEO["/api/trails/geojson"]
        API_ENR["/api/trails/enrichment"]
        UI[TrailProfile.jsx]
    end

    subgraph scripts["gis/ scripts"]
        EXP[export_trails.js]
        BUILD[pyqgis/build_trail_layers.py]
        ENR[pyqgis/enrich_trails.py]
        FIND[find_trails.py]
        PLACE[pyqgis/add_place_layer.py]
    end

    subgraph data["gis/data/"]
        GJ[trails.geojson]
        GPKG[(trailfeathers.gpkg)]
        QGZ[trailfeathers.qgz]
        EJ[trail_enrichment.json]
        PJ[&lt;place&gt;.geojson]
    end

    subgraph ext["External services"]
        OSM[(Overpass / OSM)]
        NOM[Nominatim]
        METEO[Open-Meteo DEM]
        EBIRD[eBird API]
    end

    DB -- "--db" --> EXP
    DUMMY --> EXP
    EXP --> GJ
    GJ --> BUILD
    BUILD --> GPKG
    BUILD --> QGZ
    EBIRD -. optional .-> BUILD
    GJ --> ENR
    OSM --> ENR
    METEO --> ENR
    EBIRD -. optional .-> ENR
    ENR --> GPKG
    ENR --> QGZ
    ENR --> EJ
    NOM --> FIND
    OSM --> FIND
    FIND --> PJ
    PJ --> PLACE
    PLACE --> GPKG
    PLACE --> QGZ
    EJ --> API_ENR --> UI
    DB --> API_GEO
    QGZ ==> QGIS[[QGIS desktop]]
    API_GEO --> PLUGIN[[QGIS plugin]]
```

Solid arrows are required inputs, dotted arrows need `EBIRD_API_KEY`. Every PyQGIS script runs
headless under `python-qgis-ltr.bat`, bootstraps `QgsApplication`, writes through
`QgsVectorFileWriter` into the shared GeoPackage, and saves the `.qgz` project so QGIS opens
straight onto the result.

## 1. Export trail data

```
node gis/export_trails.js        # uses copyAPIparkData dummy trails, no DB required
node gis/export_trails.js --db   # pulls from MySQL through the Sequelize model
```

## 2. Build the QGIS project (headless)

```mermaid
flowchart TD
    A[QgsApplication.initQgis] --> B[Load trails.geojson<br/>QgsVectorLayer ogr]
    B --> C[Write layer trails<br/>GPKG CreateOrOverwriteFile]
    B --> D[Buffer each point 2 km<br/>EPSG:4326 → 3857 → buffer → 4326]
    D --> E[Write layer trail_buffers]
    B --> F{EBIRD_API_KEY?}
    F -- yes --> G[obs/geo/recent per trail] --> H[Write layer ebird_sightings]
    F -- no --> I[skip]
    C & E & H --> J[Style: categorized by difficulty,<br/>labels, buffer fill, OSM XYZ basemap]
    J --> K[Default view extent = trails bbox]
    K --> L[project.write trailfeathers.qgz]
    L --> M[removeAllMapLayers → exitQgis]
```

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

## 3. Enrich trails (OSM linework, elevation, bird score)

```mermaid
flowchart TD
    A[Read trails.geojson] --> B[One Overpass query:<br/>path/footway/track/cycleway<br/>around:3000 m of every trailhead]
    B --> C{Mirror OK?}
    C -- overpass-api.de --> D[Save osm_lines_cache.json]
    C -- kumi.systems --> D
    C -- private.coffee --> D
    C -- all fail --> E{Cache file?}
    E -- yes --> D
    E -- no --> F{trail_lines in gpkg?}
    F -- yes --> G[Rebuild elements<br/>from GeoPackage]
    F -- no --> X[RuntimeError]
    D & G --> H[Assign each way to<br/>nearest trailhead]
    H --> I[Write layer trail_lines]
    H --> J[Longest segment per trail<br/>sample every ~100 m]
    J --> K[Open-Meteo elevation<br/>100 points per request]
    K --> L[gain / loss / min / max]
    L --> M[Write layer elevation_samples]
    A --> N{EBIRD_API_KEY?}
    N -- yes --> O[ref/hotspot/geo 10 km<br/>score = 100 × species / best]
    N -- no --> P[bird fields null]
    L & O & P --> Q[trail_enrichment.json]
    I & M --> R[Re-open .qgz, add styled<br/>trail_lines + elevation_samples, save]
```

```
C:\OSGeo4Win\python-qgis-ltr.bat gis\pyqgis\enrich_trails.py
```

Adds two layers to the GeoPackage and project, and writes `gis/data/trail_enrichment.json`:

| layer / field       | source                                                        |
|---------------------|---------------------------------------------------------------|
| trail_lines         | OSM path/footway/track/cycleway ways within 3 km of each trailhead (Overpass) |
| elevation_samples   | points every ~100 m along the longest segment, elevation from Open-Meteo (SRTM/Copernicus DEM) |
| elev_gain_m etc.    | computed from the samples                                     |
| bird_score          | 0-100, scaled from all-time species count of the richest eBird hotspot within 10 km (needs `EBIRD_API_KEY`) |

The Express server exposes the JSON at `GET /api/trails/enrichment`, and the trail profile page shows it.

## 4. Find trails in a parish / county

```mermaid
flowchart LR
    A["find_trails.py 'East Carroll Parish'"] --> B[Nominatim geocode → bbox]
    B --> C[Overpass: trails, parks,<br/>reserves, camp/picnic sites]
    C --> D[&lt;place&gt;.geojson<br/>lines / polygons / points]
    D --> E[add_place_layer.py]
    E --> F[&lt;place&gt;_tracks<br/>unnamed track, grey]
    E --> G[&lt;place&gt;_paths<br/>unnamed path/footway, orange]
    E --> H[&lt;place&gt;_named_trails<br/>red, label along line]
    H --> I[&lt;place&gt;_trail_names<br/>midpoint points → GPKG,<br/>bold label at every scale]
    E --> J[&lt;place&gt;_sites<br/>green diamonds]
    F & G & H & I & J --> K[Default view = place bbox<br/>project.write]
```

No QGIS needed. Geocodes the place with Nominatim and pulls trails, parks, nature reserves and camp/picnic sites from OSM:

```
python gis/find_trails.py "East Carroll Parish" --state Louisiana
python gis/find_trails.py "Caddo Parish" --no-tracks     # drop farm/levee tracks
```

Output is `gis/data/<place>.geojson` (drag into QGIS) plus a printed table. To add it to the
TrailFeathers project as separate layers (named ways red with along-line labels, a `trail_names`
point layer that keeps every name visible at any scale, paths orange, tracks grey, sites green) and
make it the default view:

```
C:\OSGeo4Win\python-qgis-ltr.bat gis\pyqgisdd_place_layer.py gis\data\east_carroll_parish.geojson
```

Note the search uses the geocoded bounding box, so results near parish borders can spill into neighbours.

## 5. QGIS plugin

```mermaid
sequenceDiagram
    actor U as User
    participant Q as QGIS
    participant P as TrailFeathers plugin
    participant S as Express server<br/>localhost:5555
    participant E as eBird API

    U->>Q: Plugins ▸ TrailFeathers ▸ Settings
    Q->>P: settings()
    P->>P: QgsSettings trailfeathers/server_url, ebird_key

    U->>Q: TrailFeathers ▸ Load trails
    Q->>P: load_trails()
    P->>S: GET /api/trails/geojson
    alt server up
        S-->>P: FeatureCollection
    else server down
        P->>P: read gis/data/trails.geojson
    end
    P->>Q: add layer "trails",<br/>categorized by difficulty, zoom to extent

    U->>Q: select trail point(s)
    U->>Q: TrailFeathers ▸ eBird near selected trail
    Q->>P: ebird_near_trail()
    loop each selected feature
        P->>E: GET data/obs/geo/recent?lat&lng&dist=10&back=14<br/>X-eBirdApiToken
        E-->>P: observations[]
    end
    P->>Q: add memory layer "ebird_sightings"<br/>(purple triangles) + message bar count
```

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

- Store enrichment in the `trails` table instead of a JSON file so it survives re-seeding.
- Swap Open-Meteo for USGS 3DEP (10 m) via the EPQS API for better Louisiana relief.
- Run the builder on a schedule and serve the GeoPackage as vector tiles with `tipg` or `pg_tileserv`.
- Render `trail_lines` in the React app with Leaflet so users see the actual route, not just a pin.
