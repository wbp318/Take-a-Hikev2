# TODO

## Parish trail searches

Run for each parish, then load into the project:

```
python gis/find_trails.py "<Parish Name> Parish" --state Louisiana
C:\OSGeo4W\bin\python-qgis-ltr.bat gis\pyqgis\add_place_layer.py gis\data\<parish_name>_parish.geojson
```

Done:

- [x] East Carroll
- [x] West Carroll

Remaining (62):

- [ ] Acadia
- [ ] Allen
- [ ] Ascension
- [ ] Assumption
- [ ] Avoyelles
- [ ] Beauregard
- [ ] Bienville
- [ ] Bossier
- [ ] Caddo
- [ ] Calcasieu
- [ ] Caldwell
- [ ] Cameron
- [ ] Catahoula
- [ ] Claiborne
- [ ] Concordia
- [ ] De Soto
- [ ] East Baton Rouge
- [ ] East Feliciana
- [ ] Evangeline
- [ ] Franklin
- [ ] Grant
- [ ] Iberia
- [ ] Iberville
- [ ] Jackson
- [ ] Jefferson
- [ ] Jefferson Davis
- [ ] Lafayette
- [ ] Lafourche
- [ ] LaSalle
- [ ] Lincoln
- [ ] Livingston
- [ ] Madison
- [ ] Morehouse
- [ ] Natchitoches
- [ ] Orleans
- [ ] Ouachita
- [ ] Plaquemines
- [ ] Pointe Coupee
- [ ] Rapides
- [ ] Red River
- [ ] Richland
- [ ] Sabine
- [ ] St. Bernard
- [ ] St. Charles
- [ ] St. Helena
- [ ] St. James
- [ ] St. John the Baptist
- [ ] St. Landry
- [ ] St. Martin
- [ ] St. Mary
- [ ] St. Tammany
- [ ] Tangipahoa
- [ ] Tensas
- [ ] Terrebonne
- [ ] Union
- [ ] Vermilion
- [ ] Vernon
- [ ] Washington
- [ ] Webster
- [ ] West Baton Rouge
- [ ] West Feliciana
- [ ] Winn

Notes:

- Overpass public mirrors rate-limit; space runs out or add a `--sleep` option to `find_trails.py` for batch runs.
- Searches use the geocoded bounding box, so results spill into neighbouring parishes. Clipping to the parish polygon (Nominatim `polygon_geojson=1`) would fix that.
- Track counts reflect OSM mapper effort, not real trails (see East vs West Carroll). Filter on paths, footways and named ways when judging a parish.

## Other

- [ ] Rotate the old RapidAPI key that is still in upstream git history.
- [ ] Store enrichment in the `trails` table instead of `trail_enrichment.json`.
- [ ] Render `trail_lines` in the React app with Leaflet.
- [ ] Swap Open-Meteo for USGS 3DEP (10 m) elevation.
- [ ] Run the app end to end with a `.env` and confirm the enrichment panel renders.
