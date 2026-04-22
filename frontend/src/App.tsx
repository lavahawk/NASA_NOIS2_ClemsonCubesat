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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const DEFAULT_BBOX = '-179.2,18.9,-66.9,71.4';

const wildfireLayerStyle: LayerProps = {
  id: 'wildfires-point-layer',
  type: 'circle',
  paint: {
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      2, 1.5,   
      5, 2.5,   
      8, [      
        'interpolate', ['linear'], ['get', 'frp'],
        0, 4,      
        100, 7,    
        500, 12    
      ]
    ],
    // Custom Palette: Light Orange -> Pink -> Light Red -> Dark Solid Red
    'circle-color': [
      'step',
      ['get', 'frp'],
      '#FF9E5E', // 0-10: Light Orange
      10, '#FF7A8A', // 10-50: Peachy Pink
      50, '#FF529A', // 50-100: Bright Pink
      100, '#FF3366', // 100-250: Light Red / Watermelon
      250, '#D90000', // 250-500: Solid Red
      500, '#8B0000', // 500-1000: Dark Solid Red
      1000, '#4A0000' // >1000: Very Dark Maroon Red
    ],
    'circle-stroke-width': [
      'interpolate', ['linear'], ['zoom'],
      4, 0, 
      7, 1.5  
    ],
    // White borders make dark reds and pinks stand out clearly
    'circle-stroke-color': '#ffffff',
  },
};

const wildfirePolygonLayerStyle: LayerProps = {
  id: 'wildfires-polygon-layer',
  type: 'fill',
  filter: ['==', '$type', 'Polygon'],
  paint: {
    'fill-color': '#4d4dff',
    'fill-opacity': 0.4,
  },
};

const wildfirePolygonOutlineStyle: LayerProps = {
  id: 'wildfires-polygon-outline',
  type: 'line',
  filter: ['==', '$type', 'Polygon'],
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
      geometry: { type: 'LineString', coordinates: [[-180, lat], [180, lat]] },
      properties: { kind: 'latitude', value: lat },
    });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [-178, lat] }, properties: { label: formatLat(lat), kind: 'latitude' } });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [178, lat] }, properties: { label: formatLat(lat), kind: 'latitude' } });
  }

  for (let lng = -180; lng <= 180; lng += step) {
    lineFeatures.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[lng, -80], [lng, 80]] },
      properties: { kind: 'longitude', value: lng },
    });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [lng, 78] }, properties: { label: formatLng(lng), kind: 'longitude' } });
    labelFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [lng, -78] }, properties: { label: formatLng(lng), kind: 'longitude' } });
  }

  return {
    lines: { type: 'FeatureCollection', features: lineFeatures } as GeoJSON.FeatureCollection,
    labels: { type: 'FeatureCollection', features: labelFeatures } as GeoJSON.FeatureCollection,
  };
}

function getPrevious24HoursQuery() {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  return { startTime: start.toISOString(), endTime: end.toISOString(), bbox: DEFAULT_BBOX };
}

function normalizePointsResponse(data: any): FireCollection {
  const features = data?.features || data?.points?.features || data?.points || [];
  if (Array.isArray(features)) {
    return { type: 'FeatureCollection', features: features.map((f: any) => ({ ...f, type: 'Feature' })) };
  }
  return emptyFeatureCollection;
}

function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const activeFetchIdRef = useRef(0);

  const [wildfires, setWildfires] = useState<FireCollection>(emptyFeatureCollection);
  const [loading, setLoading] = useState(false);
  const [bounds, setBounds] = useState<maplibregl.LngLatBounds | null>(null);

  const [showHotspots, setShowHotspots] = useState(true);
  const [showPerimeters, setShowPerimeters] = useState(true);
  const [isDashboardOpen, setIsDashboardOpen] = useState(true);
  const [isGlobe, setIsGlobe] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom] = useState(4);
  const [hoverCoords, setHoverCoords] = useState<{ lng: number; lat: number } | null>(null);
  const [selectedFire, setSelectedFire] = useState<{ lng: number; lat: number; props: FireProperties } | null>(null);
  const [debugMessage, setDebugMessage] = useState('No points loaded yet');
  const queryPreview = useMemo(() => getPrevious24HoursQuery(), []);

  const flyToFire = useCallback((lng: number, lat: number, props: FireProperties) => {
    if (!mapRef.current) return;
    mapRef.current.flyTo({ center: [lng, lat], zoom: 12, essential: true, duration: 2000 });
    setSelectedFire({ lng, lat, props });
  }, []);

  const fetchNASAData = useCallback(async () => {
    const fetchId = activeFetchIdRef.current + 1;
    activeFetchIdRef.current = fetchId;
    setLoading(true);
    setWildfires(emptyFeatureCollection);
    setDebugMessage('Querying /v1/points...');
    const query = getPrevious24HoursQuery();
    const baseParams = { start_time: query.startTime, end_time: query.endTime, bbox: query.bbox };

    try {
      const allFeatures: GeoJSON.Feature<GeoJSON.Geometry, FireProperties>[] = [];
      let nextCursor: string | null = null;
      let hasMore = true;
      let pageCount = 0;

      while (hasMore) {
        pageCount += 1;
        const params = new URLSearchParams({ ...baseParams, ...(nextCursor ? { cursor: nextCursor } : {}) });
        const url = `${API_BASE_URL}/v1/points?${params.toString()}`;
        const response = await fetch(url);

        if (!response.ok) throw new Error(`API Connection Failed: ${response.status}`);

        const data = await response.json();
        const collection = normalizePointsResponse(data);

        allFeatures.push(...collection.features);
        if (activeFetchIdRef.current !== fetchId) return;

        setDebugMessage(`Loaded ${allFeatures.length} points across ${pageCount} page(s)`);
        setWildfires({ type: 'FeatureCollection', features: [...allFeatures] });

        hasMore = Boolean(data?.has_more);
        nextCursor = typeof data?.next_cursor === 'string' ? data.next_cursor : null;
      }
    } catch (err) {
      if (activeFetchIdRef.current === fetchId) {
        setDebugMessage(err instanceof Error ? err.message : 'API query failed');
      }
    } finally {
      if (activeFetchIdRef.current === fetchId) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNASAData();
  }, [fetchNASAData]);

  useEffect(() => {
    if (!selectedFire) return;
    const isPolygon = selectedFire.props.$type === 'Polygon';
    if ((!showHotspots && !isPolygon) || (!showPerimeters && isPolygon)) {
      setSelectedFire(null);
    }
  }, [showHotspots, showPerimeters, selectedFire]);

  const visibleWildfires = useMemo(() => {
    if (!bounds || !wildfires.features.length) return [];
    
    const filtered = wildfires.features.filter(f => {
      if (f.geometry?.type === 'Point') {
        const [lng, lat] = f.geometry.coordinates as [number, number];
        return bounds.contains([lng, lat]);
      }
      return true; 
    });

    return filtered.sort((a, b) => {
      const frpA = a.properties?.frp ?? 0;
      const frpB = b.properties?.frp ?? 0;
      return frpB - frpA; 
    });
  }, [wildfires, bounds]);

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
    setBounds(e.target.getBounds());
  }, []);

  const onMove = useCallback((e: any) => {
    setZoom(e.viewState.zoom);
    setBounds(e.target.getBounds());
  }, []);

  const onMapClick = useCallback((event: any) => {
    const feature = event.features && event.features[0];
    if (feature) {
      setSelectedFire({ lng: event.lngLat.lng, lat: event.lngLat.lat, props: feature.properties ?? {} });
    } else {
      setSelectedFire(null);
    }
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', fontFamily: 'sans-serif', overflow: 'hidden' }}>
      <div className="map-container" style={{ flex: 1, position: 'relative' }}>
        <Map
          style={{ width: '100%', height: '100%', backgroundColor: isGlobe ? '#0f172a' : 'transparent' }}
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
          cursor="default"
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

          {wildfires.features.length > 0 && showPerimeters && (
            <Source id="wildfires-polygon-data" type="geojson" data={wildfires}>
              <Layer {...wildfirePolygonLayerStyle} />
              <Layer {...wildfirePolygonOutlineStyle} />
            </Source>
          )}

          {wildfires.features.length > 0 && showHotspots && (
            <Source id="wildfires-data" type="geojson" data={wildfires}>
              <Layer {...wildfireLayerStyle} />
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
              position: 'absolute', bottom: '20px', left: '20px', zIndex: 10,
              backgroundColor: 'rgba(0, 0, 0, 0.75)', color: '#fff',
              padding: '8px 12px', borderRadius: '6px', fontFamily: 'monospace',
            }}
          >
            Lng: {hoverCoords.lng.toFixed(4)} | Lat: {hoverCoords.lat.toFixed(4)}
          </div>
        )}

        <div style={{ position: 'absolute', top: '20px', right: '20px', zIndex: 10, display: 'flex', gap: '10px' }}>
          <button onClick={() => setShowGrid(!showGrid)} style={{ padding: '12px', background: showGrid ? '#ff8c00' : 'white', borderRadius: '8px' }}>
            Grid Lines: {showGrid ? 'ON' : 'OFF'}
          </button>
          <button onClick={() => setIsGlobe(!isGlobe)} style={{ padding: '12px', background: 'white', borderRadius: '8px' }}>
            {isGlobe ? 'Switch to 2D' : 'Switch to 3D'}
          </button>
          {!isDashboardOpen && (
            <button onClick={() => setIsDashboardOpen(true)} style={{ padding: '12px', backgroundColor: '#333', color: 'white', borderRadius: '8px' }}>
              Enter Dashboard
            </button>
          )}
        </div>
      </div>

      {isDashboardOpen && (
        <aside style={{ width: '350px', padding: '20px', backgroundColor: '#f8f9fa', borderLeft: '1px solid #ccc', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
            <h2 style={{ margin: 0 }}>NOIS2 Tracker</h2>
            <button onClick={() => setIsDashboardOpen(false)} style={{ padding: '6px 12px', backgroundColor: 'black', color: 'white', borderRadius: '6px' }}>Exit ✖</button>
          </div>

          <div style={{ padding: '15px', backgroundColor: '#fff3e0', borderRadius: '10px', marginBottom: '20px', border: '2px solid #ff8c00' }}>
            <h4 style={{ margin: '0 0 10px 0', color: '#e65100', fontSize: '16px' }}>📡 Live API Params</h4>
            <div style={{ fontSize: '13px', fontFamily: 'monospace', lineHeight: '1.6' }}>
              <strong style={{ color: '#333' }}>BBOX:</strong><br />
              <span style={{ color: '#d32f2f' }}>{queryPreview.bbox}</span><br />
              <strong style={{ color: '#333' }}>Range:</strong><br />
              Previous 24h UTC
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button onClick={() => setShowHotspots(!showHotspots)} style={{ padding: '12px', border: 'none', borderRadius: '6px', color: 'white', fontWeight: 'bold', backgroundColor: showHotspots ? '#ff4d4d' : '#9ca3af' }}>
              Hotspots: {showHotspots ? 'ON' : 'OFF'}
            </button>
            <button onClick={() => setShowPerimeters(!showPerimeters)} style={{ padding: '12px', border: 'none', borderRadius: '6px', color: 'white', fontWeight: 'bold', backgroundColor: showPerimeters ? '#4d4dff' : '#9ca3af' }}>
              Perimeters: {showPerimeters ? 'ON' : 'OFF'}
            </button>
          </div>

          <div style={{ marginTop: '20px', padding: '15px', backgroundColor: 'white', borderRadius: '8px', flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <h3 style={{ margin: '0 0 10px 0' }}>Statistics</h3>
            <p style={{ fontWeight: 'bold' }}>
              Visible in Map: {loading ? 'Loading...' : visibleWildfires.length} 
              <span style={{ fontWeight: 'normal', fontSize: '12px', marginLeft: '5px', color: '#6b7280' }}>
                 (Total: {wildfires.features.length})
              </span>
            </p>
            <p style={{ fontSize: '12px', color: '#4b5563', marginTop: 0 }}>
              Debug: {debugMessage}
            </p>

            <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {visibleWildfires.map((f: any, i: number) => {
                const lng = f.geometry?.coordinates?.[0];
                const lat = f.geometry?.coordinates?.[1];

                return (
                  <div 
                    key={i} 
                    onClick={() => {
                      if (lng !== undefined && lat !== undefined) {
                        flyToFire(lng, lat, f.properties);
                      }
                    }}
                    style={{ 
                      padding: '10px', 
                      backgroundColor: '#f8f9fa', 
                      border: '1px solid #e5e7eb', 
                      borderRadius: '6px', 
                      fontSize: '12px',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s, background-color 0.2s'
                    }}
                    onMouseOver={(e) => { 
                      e.currentTarget.style.borderColor = '#ff4d4d'; 
                      e.currentTarget.style.backgroundColor = 'white'; 
                    }}
                    onMouseOut={(e) => { 
                      e.currentTarget.style.borderColor = '#e5e7eb'; 
                      e.currentTarget.style.backgroundColor = '#f8f9fa'; 
                    }}
                  >
                    <strong>ID: #{String(f?.properties?.id ?? i).substring(0, 8)}</strong>
                    <br />
                    Intensity: <span style={{ color: '#d32f2f', fontWeight: 'bold' }}>{f?.properties?.frp ?? 'N/A'} MW</span> | Conf: {f?.properties?.confidence ?? 'N/A'}
                  </div>
                );
              })}
              {!loading && visibleWildfires.length === 0 && (
                <div style={{ padding: '10px', textAlign: 'center', color: '#6b7280' }}>
                  Pan or zoom to find hotspots.
                </div>
              )}
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}

export default App;