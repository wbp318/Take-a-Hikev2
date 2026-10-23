// Export trail records to GeoJSON for QGIS.
// Usage: node gis/export_trails.js            -> uses dummy data (no DB needed)
//        node gis/export_trails.js --db       -> reads from MySQL via Sequelize
const fs = require('fs');
const path = require('path');

const out = path.join(__dirname, 'data', 'trails.geojson');

function toFeature(t) {
  const lat = parseFloat(t.lat);
  const lon = parseFloat(t.lon);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lon, lat] },
    properties: {
      id: t.id,
      name: t.name,
      length_mi: parseFloat(t.length) || null,
      difficulty: t.difficulty || 'Unknown',
      rating: t.rating ?? null,
      city: t.city,
      region: t.region,
      country: t.country,
      features: t.features,
      url: t.url,
      thumbnail: t.thumbnail,
      description: t.description,
    },
  };
}

async function load() {
  if (process.argv.includes('--db')) {
    const { Trails } = require('../server/database/models/trails.js');
    const rows = await Trails.findAll({ raw: true });
    return rows;
  }
  return require('../copyAPIparkData/dummyDataCopy.js').dummyParkData;
}

load().then((rows) => {
  const fc = {
    type: 'FeatureCollection',
    features: rows.map(toFeature).filter(Boolean),
  };
  fs.writeFileSync(out, JSON.stringify(fc, null, 2));
  console.log(`Wrote ${fc.features.length} trails to ${out}`);
  process.exit(0);
}).catch((e) => { console.error(e); process.exit(1); });
