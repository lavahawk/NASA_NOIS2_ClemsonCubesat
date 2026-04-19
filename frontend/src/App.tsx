import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Map, { Source, Layer, Popup, type LayerProps } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './App.css';

type FireProperties = {
  id?: string | number;
  frp?: number;
  confidence?: number | string;
  satellite?: string;
  [key: string]: any;
};

type FireCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, FireProperties>;

const emptyFeatureCollection: FireCollection = {
  type: 'FeatureCollection',
  features: [],
};

const wildfireLayerStyle: LayerProps = {
  id: 'wildfires-point-layer',
  type: 'circle',
  filter: ['==', ['geometry-type'], 'Point'],
  paint: {
    'circle-radius': 6,
    'circle-color': '#ff4d4d',
    'circle-stroke-width': 1,
    'circle-stroke-color': '#ffffff',
  },
};

const wildfirePolygonLayerStyle: LayerProps = {
  id: 'wildfires-polygon-layer',
  type: 'fill',
  filter: ['==', ['geometry-type'], 'Polygon'],
  paint: {
    'fill-color': '#4d4dff',
    'fill-opacity': 0.4,
  },
};

const wildfirePolygonOutlineStyle: LayerProps = {
  id: 'wildfires-polygon-outline',
  type: 'line',
  filter: ['==', ['geometry-type'], 'Polygon'],
  paint: {
    'line-color': '#4d4dff',
    'line-width': 2,
  },
};

const gridLineStyle: LayerProps = {
  id: 'latlon-grid-lines',
  type: 'line',
  paint: {
    'line-color': '#ff8c00',
    'line-width': 1.2,
    'line-opacity': 0.85,
  },
};

const gridLabelStyle: LayerProps = {
  id: 'latlon-grid-labels',
  type: 'symbol',
  layout: {
    'text-field': ['get', 'label'],
    'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
    'text-size': ['interpolate', ['linear'], ['zoom'], 2, 10, 6, 14, 10, 24],
    'text-allow-overlap': false,
    'text-ignore-placement': false,
    'text-anchor': 'center',
    'text-offset': [0, 0],
  },
  paint: {
    'text-color': '#ff8c00',
    'text-halo-color': '#ffffff',
    'text-halo-width': 2,
  },
};

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
    lineFeatures.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [[-180, lat], [180, lat]],
      },
      properties: { kind: 'latitude', value: lat },
    });

    labelFeatures.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-178, lat] },
      properties: { label: formatLat(lat), kind: 'latitude' },
    });

    labelFeatures.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [178, lat] },
      properties: { label: formatLat(lat), kind: 'latitude' },
    });
  }

  for (let lng = -180; lng <= 180; lng += step) {
    lineFeatures.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [[lng, -80], [lng, 80]],
      },
      properties: { kind: 'longitude', value: lng },
    });

    labelFeatures.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, 78] },
      properties: { label: formatLng(lng), kind: 'longitude' },
    });

    labelFeatures.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, -78] },
      properties: { label: formatLng(lng), kind: 'longitude' },
    });
  }

  return {
    lines: { type: 'FeatureCollection', features: lineFeatures } as GeoJSON.FeatureCollection,
    labels: { type: 'FeatureCollection', features: labelFeatures } as GeoJSON.FeatureCollection,
  };
}

function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);

  const [wildfires, setWildfires] = useState<FireCollection>(emptyFeatureCollection);
  const [loading, setLoading] = useState(false);

  const [showHotspots, setShowHotspots] = useState(true);
  const [showPerimeters, setShowPerimeters] = useState(true);
  const [isDashboardOpen, setIsDashboardOpen] = useState(true);
  const [isGlobe, setIsGlobe] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom] = useState(4);
  const [hoverCoords, setHoverCoords] = useState<{ lng: number; lat: number } | null>(null);
  const [selectedFire, setSelectedFire] = useState<{ lng: number; lat: number; props: FireProperties } | null>(null);

  const queryParams = useMemo(
    () => ({
      start: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      end: new Date().toISOString(),
      bbox: '-125,24,-66,49',
    }),
    []
  );

  const fetchNASAData = useCallback(async () => {
    setLoading(true);

    const url = `http://localhost:8000/v1/points?start_time=${encodeURIComponent(
      queryParams.start
    )}&end_time=${encodeURIComponent(queryParams.end)}&bbox=${encodeURIComponent(queryParams.bbox)}`;

    try {
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`API Connection Failed: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      console.log('API DATA:', data);

      const collection: FireCollection =
        data?.points?.type === 'FeatureCollection'
          ? data.points
          : data?.type === 'FeatureCollection'
            ? data
            : Array.isArray(data?.features)
              ? { type: 'FeatureCollection', features: data.features }
              : Array.isArray(data?.points)
                ? { type: 'FeatureCollection', features: data.points }
                : emptyFeatureCollection;

      setWildfires(collection);
    } catch (err) {
      console.error('NASA API Error:', err);
      setWildfires(emptyFeatureCollection);
    } finally {
      setLoading(false);
    }
  }, [queryParams.start, queryParams.end, queryParams.bbox]);

  useEffect(() => {
    fetchNASAData();
  }, [fetchNASAData]);

  const gridStep = useMemo(() => {
    if (zoom <= 3) return 20;
    if (zoom <= 5) return 10;
    if (zoom <= 7) return 5;
    return 1;
  }, [zoom]);

  const gridData = useMemo(() => buildLatLonGrid(gridStep), [gridStep]);

  const onMapLoad = useCallback((e: any) => {
    mapRef.current = e.target;
    setZoom(e.target.getZoom());
  }, []);

  const onMove = useCallback((e: any) => setZoom(e.viewState.zoom), []);

  const onMapClick = useCallback((event: any) => {
    const feature = event.features && event.features[0];
    if (feature) {
      setSelectedFire({
        lng: event.lngLat.lng,
        lat: event.lngLat.lat,
        props: feature.properties ?? {},
      });
    } else {
      setSelectedFire(null);
    }
  }, []);

  const totalObjects = wildfires.features.length;

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', fontFamily: 'sans-serif', overflow: 'hidden' }}>
      <div className="map-container" style={{ flex: 1, position: 'relative' }}>
        <Map
          style={{
            width: '100%',
            height: '100%',
            backgroundColor: isGlobe ? '#0f172a' : 'transparent',
          }}
          mapLib={maplibregl}
          onLoad={onMapLoad}
          onMove={onMove}
          onClick={onMapClick}
          onMouseMove={(e) => e.lngLat && setHoverCoords({ lng: e.lngLat.lng, lat: e.lngLat.lat })}
          onMouseOut={() => setHoverCoords(null)}
          interactiveLayerIds={['wildfires-point-layer', 'wildfires-polygon-layer']}
          initialViewState={{ longitude: -98.5795, latitude: 39.8283, zoom: 4 }}
          minZoom={2.0}
          mapStyle="https://tiles.openfreemap.org/styles/liberty"
          projection={isGlobe ? { type: 'globe' } : undefined}
        >
          {showGrid && (
            <>
              <Source id="grid-lines" type="geojson" data={gridData.lines}>
                <Layer {...gridLineStyle} />
              </Source>
              <Source id="grid-labels" type="geojson" data={gridData.labels}>
                <Layer {...gridLabelStyle} />
              </Source>
            </>
          )}

          {wildfires.features.length > 0 && (
            <Source id="wildfires-data" type="geojson" data={wildfires}>
              <Layer {...wildfirePolygonLayerStyle} layout={{ visibility: showPerimeters ? 'visible' : 'none' }} />
              <Layer {...wildfirePolygonOutlineStyle} layout={{ visibility: showPerimeters ? 'visible' : 'none' }} />
              <Layer {...wildfireLayerStyle} layout={{ visibility: showHotspots ? 'visible' : 'none' }} />
            </Source>
          )}

          {selectedFire && (
            <Popup
              longitude={selectedFire.lng}
              latitude={selectedFire.lat}
              anchor="bottom"
              onClose={() => setSelectedFire(null)}
            >
              <div style={{ color: '#333' }}>
                <h3 style={{ margin: 0 }}>{selectedFire.props.satellite || 'Satellite Point'}</h3>
                <p><strong>FRP:</strong> {selectedFire.props.frp ?? 'N/A'} MW</p>
                <p><strong>Conf:</strong> {selectedFire.props.confidence ?? 'N/A'}</p>
              </div>
            </Popup>
          )}
        </Map>

        {hoverCoords && (
          <div
            style={{
              position: 'absolute',
              bottom: '20px',
              left: '20px',
              zIndex: 10,
              backgroundColor: 'rgba(0, 0, 0, 0.75)',
              color: '#fff',
              padding: '8px 12px',
              borderRadius: '6px',
              fontFamily: 'monospace',
            }}
          >
            Lng: {hoverCoords.lng.toFixed(4)} | Lat: {hoverCoords.lat.toFixed(4)}
          </div>
        )}

        <div
          style={{
            position: 'absolute',
            top: '20px',
            right: '20px',
            zIndex: 10,
            display: 'flex',
            gap: '10px',
          }}
        >
          <button
            onClick={() => setShowGrid(!showGrid)}
            style={{
              padding: '12px',
              background: showGrid ? '#ff8c00' : 'white',
              borderRadius: '8px',
            }}
          >
            Grid Lines: {showGrid ? 'ON' : 'OFF'}
          </button>

          <button
            onClick={() => setIsGlobe(!isGlobe)}
            style={{
              padding: '12px',
              background: 'white',
              borderRadius: '8px',
            }}
          >
            {isGlobe ? 'Switch to 2D' : 'Switch to 3D'}
          </button>

          {!isDashboardOpen && (
            <button
              onClick={() => setIsDashboardOpen(true)}
              style={{
                padding: '12px',
                backgroundColor: '#333',
                color: 'white',
                borderRadius: '8px',
              }}
            >
              Enter Dashboard
            </button>
          )}
        </div>
      </div>

      {isDashboardOpen && (
        <aside
          style={{
            width: '350px',
            padding: '20px',
            backgroundColor: '#f8f9fa',
            borderLeft: '1px solid #ccc',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
            <h2 style={{ margin: 0 }}>NOIS2 Tracker</h2>
            <button
              onClick={() => setIsDashboardOpen(false)}
              style={{
                padding: '6px 12px',
                backgroundColor: 'black',
                color: 'white',
                borderRadius: '6px',
              }}
            >
              Exit ✖
            </button>
          </div>

          <div
            style={{
              padding: '15px',
              backgroundColor: '#fff3e0',
              borderRadius: '10px',
              marginBottom: '20px',
              border: '2px solid #ff8c00',
            }}
          >
            <h4 style={{ margin: '0 0 10px 0', color: '#e65100', fontSize: '16px' }}>📡 Live API Params</h4>
            <div style={{ fontSize: '13px', fontFamily: 'monospace', lineHeight: '1.6' }}>
              <strong style={{ color: '#333' }}>BBOX:</strong>
              <br />
              <span style={{ color: '#d32f2f' }}>{queryParams.bbox}</span>
              <br />
              <strong style={{ color: '#333' }}>Range:</strong>
              <br />
              {queryParams.start.substring(0, 10)} - Now
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              onClick={() => setShowHotspots(!showHotspots)}
              style={{
                padding: '12px',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                fontWeight: 'bold',
                backgroundColor: showHotspots ? '#ff4d4d' : '#9ca3af',
              }}
            >
              Hotspots: {showHotspots ? 'ON' : 'OFF'}
            </button>

            <button
              onClick={() => setShowPerimeters(!showPerimeters)}
              style={{
                padding: '12px',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                fontWeight: 'bold',
                backgroundColor: showPerimeters ? '#4d4dff' : '#9ca3af',
              }}
            >
              Perimeters: {showPerimeters ? 'ON' : 'OFF'}
            </button>
          </div>

          <div
            style={{
              marginTop: '20px',
              padding: '15px',
              backgroundColor: 'white',
              borderRadius: '8px',
              flex: 1,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <h3 style={{ margin: '0 0 10px 0' }}>Statistics</h3>
            <p style={{ fontWeight: 'bold' }}>
              Total Objects: {loading ? 'Loading...' : totalObjects}
            </p>

            <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {wildfires.features.map((f: any, i: number) => (
                <div
                  key={i}
                  style={{
                    padding: '10px',
                    backgroundColor: '#f8f9fa',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                >
                  <strong>ID: #{String(f?.properties?.id ?? i).substring(0, 8)}</strong>
                  <br />
                  Intensity: {f?.properties?.frp ?? 'N/A'} MW | Conf: {f?.properties?.confidence ?? 'N/A'}
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