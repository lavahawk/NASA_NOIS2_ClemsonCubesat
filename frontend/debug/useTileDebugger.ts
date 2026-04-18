import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import type { MapEvents } from '../hooks/useMapEvents';
import { lonToTileX, latToTileY, tileToLon, tileToLat } from '../utils/tileUtils';

// --- MATH HELPERS ---

const tileToPolygon = (x: number, y: number, z: number): GeoJSON.Feature => ({
    type: 'Feature',
    geometry: {
        type: 'Polygon',
        coordinates: [[
            [tileToLon(x, z), tileToLat(y, z)],
            [tileToLon(x + 1, z), tileToLat(y, z)],
            [tileToLon(x + 1, z), tileToLat(y + 1, z)],
            [tileToLon(x, z), tileToLat(y + 1, z)],
            [tileToLon(x, z), tileToLat(y, z)],
        ]]
    },
    properties: { label: `${z}/${x}/${y}` }
});

const getVisibleTileFeatures = (map: maplibregl.Map): GeoJSON.FeatureCollection => {
    const bounds = map.getBounds();
    const z = Math.floor(map.getZoom());

    const minX = lonToTileX(bounds.getWest(), z);
    const maxX = lonToTileX(bounds.getEast(), z);
    const minY = latToTileY(bounds.getNorth(), z);
    const maxY = latToTileY(bounds.getSouth(), z);

    const features: GeoJSON.Feature[] = [];
    for (let x = minX; x <= maxX; x++)
        for (let y = minY; y <= maxY; y++)
            features.push(tileToPolygon(x, y, z));

    return { type: 'FeatureCollection', features };
};

const SOURCE_ID = 'debug-grid';

const ensureGridLayers = (map: maplibregl.Map, color: string) => {
  if (map.getSource(SOURCE_ID)) {
    // Update colors if they already exist
    if (map.getLayer('debug-grid-lines')) {
      map.setPaintProperty('debug-grid-lines', 'line-color', color);
    }
    if (map.getLayer('debug-grid-labels')) {
      map.setPaintProperty('debug-grid-labels', 'text-color', color);
    }
    return;
  }
  map.addSource(SOURCE_ID, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({
    id: 'debug-grid-lines',
    type: 'line',
    source: SOURCE_ID,
    paint: { 'line-color': color, 'line-width': 1, 'line-dasharray': [2, 2] }
  });
  map.addLayer({
    id: 'debug-grid-labels',
    type: 'symbol',
    source: SOURCE_ID,
    layout: { 'text-field': ['get', 'label'], 'text-size': 12 },
    paint: { 'text-color': color }
  });
};

const updateGrid = (map: maplibregl.Map, color: string) => {
  ensureGridLayers(map, color);
  (map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource)
    .setData(getVisibleTileFeatures(map));
};

export const useTileDebugger = (mapEvents: MapEvents, color: string = '#ff4500',  enabled: boolean) => {
  useEffect(() => {
    if (!enabled) {
      const clearGrid = (map: maplibregl.Map) => {
        const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
        if (source) {
          source.setData({ type: 'FeatureCollection', features: [] });
        }
      };

      mapEvents.onLoad(clearGrid);
      return () => {
        mapEvents.offLoad(clearGrid);
      };
    }

    const onUpdate = (map: maplibregl.Map) => updateGrid(map, color);

    mapEvents.onLoad(onUpdate);
    mapEvents.onMoveEnd(onUpdate);
    return () => {
      mapEvents.offLoad(onUpdate);
      mapEvents.offMoveEnd(onUpdate);
    };
  }, [enabled, mapEvents, color]);
};