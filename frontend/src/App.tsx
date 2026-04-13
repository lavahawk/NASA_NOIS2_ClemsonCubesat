import { useState, useEffect, useRef, useCallback } from 'react';
import Map, { Source, Layer, type LayerProps } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './App.css';
import { useTileDebugger } from './useTileDebugger'

const wildfireLayerStyle: LayerProps = {
  id: 'wildfires-point-layer',
  type: 'circle',
  filter: ['==', ['geometry-type'], 'Point'],
  paint: {
    'circle-radius': 6,
    'circle-color': '#ff4d4d',
    'circle-stroke-width': 1,
    'circle-stroke-color': '#ffffff'
  }
};

const wildfirePolygonLayerStyle: LayerProps = {
  id: 'wildfires-polygon-layer',
  type: 'fill',
  filter: ['==', ['geometry-type'], 'Polygon'],
  paint: {
    'fill-color': '#ff4d4d',
    'fill-opacity': 0.4
  }
};

const wildfirePolygonOutlineStyle: LayerProps = {
  id: 'wildfires-polygon-outline',
  type: 'line',
  filter: ['==', ['geometry-type'], 'Polygon'],
  paint: {
    'line-color': '#ff4d4d',
    'line-width': 2
  }
};

function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [wildfires, setWildfires] = useState<GeoJSON.FeatureCollection | null>(null);
  const { updateGrid } = useTileDebugger(mapRef, true);

  useEffect(() => {
    fetch('http://localhost:8000/wildfires')
      .then(response => response.json())
      .then(data => {
        console.log('Fetched wildfires:', data);
        setWildfires(data);
      })
      .catch(error => console.error('Error fetching wildfires:', error));
  }, []);

  const onMapLoad = useCallback((e: any) => {
    mapRef.current = e.target;
    updateGrid(); // Initial draw
  }, [updateGrid]);

  return (
    <div className="map-container">
      <Map
        mapLib={maplibregl}
        onLoad={onMapLoad}
        onMoveEnd={updateGrid}
        initialViewState={{
          longitude: -98.5795,
          latitude: 39.8283,
          zoom: 3
        }}
        mapStyle='https://tiles.openfreemap.org/styles/liberty'
      >
        {wildfires && (
          <Source id="wildfires-data" type="geojson" data={wildfires}>
            <Layer {...wildfirePolygonLayerStyle} />
            <Layer {...wildfirePolygonOutlineStyle} />
            <Layer {...wildfireLayerStyle} />
          </Source>
        )}
      </Map>
    </div>
  );
}

export default App;

// load in terms of tiles: 
// try to test and follow the gemini stuff ig