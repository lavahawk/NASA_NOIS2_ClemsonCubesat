import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

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

const AutoTileDebugger: React.FC = () => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [visibleTiles, setVisibleTiles] = useState<string[]>([]);

  useEffect(() => {
    if (map.current || !mapContainer.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [-82.34, 34.67],
      zoom: 4 // Start zoomed out to see the grid
    });

    const updateGrid = () => {
      if (!map.current) return;

      const bounds = map.current.getBounds();
      const z = Math.floor(map.current.getZoom());
      
      // Find the start and end tile indices for the current view
      const minX = lonToTileX(bounds.getWest(), z);
      const maxX = lonToTileX(bounds.getEast(), z);
      const minY = latToTileY(bounds.getNorth(), z);
      const maxY = latToTileY(bounds.getSouth(), z);

      const features: GeoJSON.Feature[] = [];
      const tileLabels: string[] = [];

      // Loop through all tiles in the current viewport
      for (let x = minX; x <= maxX; x++) {
        for (let y = minY; y <= maxY; y++) {
          tileLabels.push(`${z}/${x}/${y}`);

          const lonW = tileToLon(x, z);
          const latN = tileToLat(y, z);
          const lonE = tileToLon(x + 1, z);
          const latS = tileToLat(y + 1, z);

          features.push({
            type: 'Feature',
            geometry: {
              type: 'Polygon',
              coordinates: [[[lonW, latN], [lonE, latN], [lonE, latS], [lonW, latS], [lonW, latN]]]
            },
            properties: { id: `${z}/${x}/${y}` }
          });
        }
      }

      setVisibleTiles(tileLabels);

      const source = map.current.getSource('grid') as maplibregl.GeoJSONSource;
      if (source) {
        source.setData({ type: 'FeatureCollection', features });
      } else {
        map.current.addSource('grid', { type: 'geojson', data: { type: 'FeatureCollection', features } });
        map.current.addLayer({
          id: 'grid-layer',
          type: 'line',
          source: 'grid',
          paint: { 'line-color': '#ff4500', 'line-width': 2 }
        });
      }
    };

    map.current.on('load', updateGrid);
    map.current.on('moveend', updateGrid);
  }, []);

  return (
    <div style={{ position: 'relative', width: '100%', height: '600px' }}>
      <div style={{
        position: 'absolute', top: 10, right: 10, zIndex: 1, maxHeight: '200px',
        background: 'rgba(255,255,255,0.9)', padding: '10px', overflowY: 'auto', fontSize: '12px'
      }}>
        <strong>Visible Tile Requests:</strong>
        {visibleTiles.map(t => <div key={t}>{t}</div>)}
      </div>
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
    </div>
  );
};

export default AutoTileDebugger;