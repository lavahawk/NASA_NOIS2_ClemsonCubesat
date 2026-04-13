import { type RefObject } from 'react';
import maplibregl from 'maplibre-gl';

// --- MATH HELPERS ---
const lonToTileX = (lon: number, z: number) => 
  Math.floor((lon + 180) / 360 * Math.pow(2, z));

const latToTileY = (lat: number, z: number) => 
  Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, z));

const tileToLon = (x: number, z: number) => (x / Math.pow(2, z)) * 360 - 180;

const tileToLat = (y: number, z: number) => {
  const n = Math.PI - 2.0 * Math.PI * y / Math.pow(2, z);
  return 180.0 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
};

export const useTileDebugger = (mapRef: RefObject<maplibregl.Map | null>, enabled: boolean) => {
  const updateGrid = () => {
    const map = mapRef.current;
    if (!map || !enabled) return;

    const bounds = map.getBounds();
    const z = Math.floor(map.getZoom());
    
    const minX = lonToTileX(bounds.getWest(), z);
    const maxX = lonToTileX(bounds.getEast(), z);
    const minY = latToTileY(bounds.getNorth(), z);
    const maxY = latToTileY(bounds.getSouth(), z);

    const features: GeoJSON.Feature[] = [];
    for (let x = minX; x <= maxX; x++) {
      for (let y = minY; y <= maxY; y++) {
        features.push({
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[[tileToLon(x, z), tileToLat(y, z)], [tileToLon(x + 1, z), tileToLat(y, z)], [tileToLon(x + 1, z), tileToLat(y + 1, z)], [tileToLon(x, z), tileToLat(y + 1, z)], [tileToLon(x, z), tileToLat(y, z)]]]
          },
          properties: { label: `${z}/${x}/${y}` }
        });
      }
    }

    const source = map.getSource('debug-grid') as maplibregl.GeoJSONSource;
    if (source) {
      source.setData({ type: 'FeatureCollection', features });
    } else {
      map.addSource('debug-grid', { type: 'geojson', data: { type: 'FeatureCollection', features } });
      map.addLayer({
        id: 'debug-grid-lines',
        type: 'line',
        source: 'debug-grid',
        paint: { 'line-color': '#ff4500', 'line-width': 1, 'line-dasharray': [2, 2] }
      });
      map.addLayer({
        id: 'debug-grid-labels',
        type: 'symbol',
        source: 'debug-grid',
        layout: { 'text-field': ['get', 'label'], 'text-size': 12 },
        paint: { 'text-color': '#ff4500' }
      });
    }
  };

  return { updateGrid };
};