import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Map, { Source, Layer, Popup, type LayerProps } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './App.css';

// Layer Styles
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
    'fill-color': '#4d4dff',
    'fill-opacity': 0.4
  }
};

const wildfirePolygonOutlineStyle: LayerProps = {
  id: 'wildfires-polygon-outline',
  type: 'line',
  filter: ['==', ['geometry-type'], 'Polygon'],
  paint: {
    'line-color': '#4d4dff',
    'line-width': 2
  }
};

const gridLineStyle: LayerProps = {
  id: 'latlon-grid-lines',
  type: 'line',
  paint: {
    'line-color': '#ff8c00',
    'line-width': 1.2,
    'line-opacity': 0.85
  }
};

const gridLabelStyle: LayerProps = {
  id: 'latlon-grid-labels',
  type: 'symbol',
  layout: {
    'text-field': ['get', 'label'],
    'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
    'text-size': [
      'interpolate',
      ['linear'],
      ['zoom'],
      2, 10,  
      6, 14,
      10, 24  
    ],
    'text-allow-overlap': false, 
    'text-ignore-placement': false,
    'text-anchor': 'center',
    'text-offset': [0, 0]
  },
  paint: {
    'text-color': '#ff8c00',
    'text-halo-color': '#ffffff',
    'text-halo-width': 2
  }
};

// Helper Functions
function formatLat(lat: number) {
  if (lat === 0) return '0°';
  return `${Math.abs(lat)}°${lat > 0 ? 'N' : 'S'}`;
}

function formatLng(lng: number) {
  if (lng === 0) return '0°';
  return `${Math.abs(lng)}°${lng > 0 ? 'E' : 'W'}`;
}

function buildLatLonGrid(step = 10) {
  const lineFeatures: GeoJSON.Feature<GeoJSON.LineString>[] = [];
  const labelFeatures: GeoJSON.Feature<GeoJSON.Point>[] = [];

  for (let lat = -80; lat <= 80; lat += step) {
    lineFeatures.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[-180, lat], [180, lat]] }, properties: { kind: 'latitude', value: lat } });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [-178, lat] }, properties: { label: formatLat(lat), kind: 'latitude' } });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [178, lat] }, properties: { label: formatLat(lat), kind: 'latitude' } });
  }

  for (let lng = -180; lng <= 180; lng += step) {
    lineFeatures.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[lng, -80], [lng, 80]] }, properties: { kind: 'longitude', value: lng } });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [lng, 78] }, properties: { label: formatLng(lng), kind: 'longitude' } });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [lng, -78] }, properties: { label: formatLng(lng), kind: 'longitude' } });
  }

  return {
    lines: { type: 'FeatureCollection', features: lineFeatures } as GeoJSON.FeatureCollection,
    labels: { type: 'FeatureCollection', features: labelFeatures } as GeoJSON.FeatureCollection
  };
}

// Main Application
function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [wildfires, setWildfires] = useState<GeoJSON.FeatureCollection | null>(null);

  // UI State
  const [showHotspots, setShowHotspots] = useState(true);
  const [showPerimeters, setShowPerimeters] = useState(true);
  const [isDashboardOpen, setIsDashboardOpen] = useState(true);
  const [isGlobe, setIsGlobe] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom] = useState(4);
  
  // Real-time Coordinates State (Ladder has been removed)
  const [hoverCoords, setHoverCoords] = useState<{ lng: number; lat: number } | null>(null);

  // Popup State
  const [selectedFire, setSelectedFire] = useState<{ lng: number; lat: number; props: any; } | null>(null);

  // Toggle Handlers (Clears popup when layers are turned off)
  const toggleHotspots = () => {
    setShowHotspots(!showHotspots);
    setSelectedFire(null);
  };

  const togglePerimeters = () => {
    setShowPerimeters(!showPerimeters);
    setSelectedFire(null);
  };

  // Grid Calculation
  const gridStep = useMemo(() => {
    if (zoom <= 3) return 20;
    if (zoom <= 5) return 10;
    if (zoom <= 7) return 5;
    if (zoom <= 9) return 2;
    return 1;
  }, [zoom]);

  const gridData = useMemo(() => buildLatLonGrid(gridStep), [gridStep]);

  useEffect(() => {
    const mockData = {
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', geometry: { type: 'Point', coordinates: [-121.0, 39.5] }, properties: { id: 101, name: 'Camp Fire', frp: '85.2 MW', confidence: '98%', satellite: 'VIIRS' } },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [-119.5, 37.8] }, properties: { id: 102, name: 'Yosemite Complex', frp: '42.1 MW', confidence: '85%', satellite: 'MODIS' } },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [149.0, -35.0] }, properties: { id: 104, name: 'NSW Bushfire', frp: '120.5 MW', confidence: '100%', satellite: 'VIIRS' } },
        {
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [[ [-117.0, 39.0], [-116.5, 39.3], [-115.8, 38.8], [-116.2, 38.2], [-117.1, 38.1], [-117.0, 39.0] ]] },
          properties: { id: 201, name: 'Nevada Burn Area', frp: 'N/A', confidence: '100%', satellite: 'Landsat-8' }
        }
      ]
    };
    setWildfires(mockData as GeoJSON.FeatureCollection);
  }, []);

  const onMapLoad = useCallback((e: any) => {
    mapRef.current = e.target;
    setZoom(e.target.getZoom());
  }, []);

  const onMove = useCallback((e: any) => setZoom(e.viewState.zoom), []);
  const onMapClick = useCallback((event: any) => {
    const feature = event.features && event.features[0];
    if (feature) {
      setSelectedFire({ lng: event.lngLat.lng, lat: event.lngLat.lat, props: feature.properties });
    } else {
      setSelectedFire(null);
    }
  }, []);

  const onMouseMove = useCallback((e: any) => {
    // Update lat/lng coordinates only
    if (e.lngLat) {
      setHoverCoords({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    }
  }, []);

  const onMouseOut = useCallback(() => {
    setHoverCoords(null);
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', fontFamily: 'sans-serif', overflow: 'hidden' }}>
      
      {/* 1. Main Map View */}
      <div className="map-container" style={{ flex: 1, position: 'relative' }}>

        <Map
          style={{ width: '100%', height: '100%', backgroundColor: isGlobe ? '#0f172a' : 'transparent' }}
          mapLib={maplibregl}
          onLoad={onMapLoad}
          onMove={onMove}
          onClick={onMapClick}
          onMouseMove={onMouseMove}
          onMouseOut={onMouseOut}
          interactiveLayerIds={['wildfires-point-layer', 'wildfires-polygon-layer']}
          initialViewState={{ longitude: -98.5795, latitude: 39.8283, zoom: 4 }}
          minZoom={1.5} // Prevents user from zooming out too far
          mapStyle="https://tiles.openfreemap.org/styles/liberty"
          renderWorldCopies={false}
          projection={isGlobe ? { type: 'globe' } : undefined}
          cursor={selectedFire ? 'pointer' : 'auto'}
        >
          {showGrid && (
            <>
              <Source id="grid-lines" type="geojson" data={gridData.lines}><Layer {...gridLineStyle} /></Source>
              <Source id="grid-labels" type="geojson" data={gridData.labels}><Layer {...gridLabelStyle} /></Source>
            </>
          )}

          {wildfires && (
            <Source id="wildfires-data" type="geojson" data={wildfires}>
              <Layer {...wildfirePolygonLayerStyle} layout={{ visibility: showPerimeters ? 'visible' : 'none' }} />
              <Layer {...wildfirePolygonOutlineStyle} layout={{ visibility: showPerimeters ? 'visible' : 'none' }} />
              <Layer {...wildfireLayerStyle} layout={{ visibility: showHotspots ? 'visible' : 'none' }} />
            </Source>
          )}

          {selectedFire && (
            <Popup longitude={selectedFire.lng} latitude={selectedFire.lat} anchor="bottom" onClose={() => setSelectedFire(null)} closeOnClick={false} style={{ padding: '10px', borderRadius: '8px' }}>
              <div style={{ color: '#333' }}>
                <h3 style={{ margin: '0 0 8px 0', borderBottom: '1px solid #ccc', paddingBottom: '4px' }}>{selectedFire.props.name || `Fire ID: ${selectedFire.props.id}`}</h3>
                <p style={{ margin: '4px 0', fontSize: '13px' }}><strong>Intensity (FRP):</strong> {selectedFire.props.frp}</p>
                <p style={{ margin: '4px 0', fontSize: '13px' }}><strong>Confidence:</strong> {selectedFire.props.confidence}</p>
                <p style={{ margin: '4px 0', fontSize: '13px' }}><strong>Satellite:</strong> {selectedFire.props.satellite}</p>
              </div>
            </Popup>
          )}
        </Map>

        {/* Live Coordinate HUD (Bottom Left) */}
        {hoverCoords && (
          <div style={{
            position: 'absolute', bottom: '20px', left: '20px', zIndex: 10,
            backgroundColor: 'rgba(0, 0, 0, 0.75)', color: '#fff',
            padding: '8px 12px', borderRadius: '6px', fontFamily: 'monospace',
            fontSize: '13px', pointerEvents: 'none', boxShadow: '0 2px 4px rgba(0,0,0,0.3)'
          }}>
            Lng: {hoverCoords.lng.toFixed(4)} | Lat: {hoverCoords.lat.toFixed(4)}
          </div>
        )}

        {/* 2. Top-Right Buttons */}
        <div style={{ position: 'absolute', top: '20px', right: '20px', zIndex: 10, display: 'flex', gap: '10px' }}>
          <button
            onClick={() => setShowGrid(!showGrid)}
            style={{ padding: '12px 16px', backgroundColor: showGrid ? '#ff8c00' : 'white', color: showGrid ? 'white' : '#333', border: '1px solid #ccc', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}
          >
            {showGrid ? 'Grid Lines: ON' : 'Grid Lines: OFF'}
          </button>

          <button
            onClick={() => setIsGlobe(!isGlobe)}
            style={{ padding: '12px 24px', backgroundColor: 'white', color: '#333', border: '1px solid #ccc', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}
          >
            {isGlobe ? 'Switch to 2D' : 'Switch to 3D'}
          </button>

          {!isDashboardOpen && (
            <button
              onClick={() => setIsDashboardOpen(true)}
              style={{ padding: '12px 24px', backgroundColor: '#333', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}
            >
              Enter Dashboard ➔
            </button>
          )}
        </div>
      </div>

      {/* 3. Dashboard Sidebar with Statistics List */}
      {isDashboardOpen && (
        <aside style={{ width: '300px', padding: '20px', backgroundColor: '#f8f9fa', borderLeft: '1px solid #ccc', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 style={{ margin: 0 }}>NOIS2 Dashboard</h2>
            <button
              onClick={() => setIsDashboardOpen(false)}
              style={{ padding: '6px 12px', backgroundColor: 'black', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', fontSize: '12px' }}
            >
              Exit ✖
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              onClick={toggleHotspots}
              style={{ padding: '12px', border: 'none', borderRadius: '6px', color: 'white', fontWeight: 'bold', cursor: 'pointer', backgroundColor: showHotspots ? '#ff4d4d' : '#9ca3af' }}
            >
              Hotspot Points {showHotspots ? 'ON' : 'OFF'}
            </button>

            <button
              onClick={togglePerimeters}
              style={{ padding: '12px', border: 'none', borderRadius: '6px', color: 'white', fontWeight: 'bold', cursor: 'pointer', backgroundColor: showPerimeters ? '#4d4dff' : '#9ca3af' }}
            >
              Fire Perimeters {showPerimeters ? 'ON' : 'OFF'}
            </button>
          </div>

          {/* Vertical Fire Data List */}
          <div style={{ marginTop: '30px', padding: '15px', backgroundColor: 'white', borderRadius: '6px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: '16px' }}>Statistics</h3>
            <p style={{ margin: '0 0 15px 0', fontSize: '14px', color: '#333', fontWeight: 'bold' }}>
              Total Objects: {wildfires ? wildfires.features.length : 'Loading...'}
            </p>

            <div style={{ overflowY: 'auto', paddingRight: '5px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {wildfires?.features.map((feature: any, idx: number) => (
                <div key={idx} style={{ padding: '10px', backgroundColor: '#f8f9fa', border: '1px solid #e5e7eb', borderRadius: '6px', fontSize: '13px' }}>
                  <div style={{ fontWeight: 'bold', marginBottom: '4px', color: '#111' }}>
                    {feature.properties.name} <span style={{ fontWeight: 'normal', color: '#666' }}>(#{feature.properties.id})</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#444', marginBottom: '2px' }}>
                    <span><strong>Intensity:</strong> {feature.properties.frp}</span>
                    <span><strong>Conf:</strong> {feature.properties.confidence}</span>
                  </div>
                  <div style={{ color: '#444' }}>
                    <strong>Satellite:</strong> {feature.properties.satellite}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}

export default App;