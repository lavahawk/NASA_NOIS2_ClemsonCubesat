import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Map, { Source, Layer, Popup } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './App.css';

import type { FireProperties, FireCollection } from './types';
import { emptyFireCollection } from './types';
import {
  wildfireLayerStyle,
  wildfirePolygonLayerStyle,
  wildfirePolygonOutlineStyle,
  gridLineStyle,
  gridLabelStyle,
} from './mapStyles';
import {
  API_BASE_URL,
  getPrevious24HoursQuery,
  buildLatLonGrid,
  normalizePointsResponse,
} from './utils';
import Dashboard from './components/Dashboard';

function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const activeFetchIdRef = useRef(0);

  const [wildfires, setWildfires] = useState<FireCollection>(emptyFireCollection);
  const [loading, setLoading] = useState(false);
  const [bounds, setBounds] = useState<maplibregl.LngLatBounds | null>(null);

  const [showHotspots, setShowHotspots] = useState(true);
  const [showPerimeters, setShowPerimeters] = useState(true);
  const [isDashboardOpen, setIsDashboardOpen] = useState(true);
  const [isGlobe, setIsGlobe] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom] = useState(4);
  const [hoverCoords, setHoverCoords] = useState<{ lng: number; lat: number } | null>(null);
  
  const [selectedFire, setSelectedFire] = useState<{ lng: number; lat: number; props: FireProperties; isPolygon: boolean } | null>(null);
  
  const [debugMessage, setDebugMessage] = useState('No points loaded yet');
  const queryPreview = useMemo(() => getPrevious24HoursQuery(), []);

  const flyToFire = useCallback((lng: number, lat: number, props: FireProperties) => {
    if (!mapRef.current) return;
    mapRef.current.flyTo({ center: [lng, lat], zoom: 12, essential: true, duration: 2000 });
    setSelectedFire({ lng, lat, props, isPolygon: false });
  }, []);

  const fetchNASAData = useCallback(async () => {
    const fetchId = activeFetchIdRef.current + 1;
    activeFetchIdRef.current = fetchId;
    setLoading(true);
    setWildfires(emptyFireCollection);
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
    const isPolygon = selectedFire.isPolygon; 
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
      setSelectedFire({ 
        lng: event.lngLat.lng, 
        lat: event.lngLat.lat, 
        props: feature.properties ?? {},
        isPolygon: feature.geometry.type === 'Polygon'
      });
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

          {wildfires.features.length > 0 && (
            <Source id="wildfires-data" type="geojson" data={wildfires}>
              {showPerimeters && (
                <>
                  <Layer {...wildfirePolygonLayerStyle} />
                  <Layer {...wildfirePolygonOutlineStyle} />
                </>
              )}
              {showHotspots && (
                <Layer {...wildfireLayerStyle} />
              )}
            </Source>
          )}

          {selectedFire && (
            <Popup
              longitude={selectedFire.lng}
              latitude={selectedFire.lat}
              anchor="bottom"
              onClose={() => setSelectedFire(null)}
              closeButton={true}
            >
              {/* SOLID UI: Thick borders and block shadows */}
              <div style={{ 
                color: '#1a1a1a', 
                backgroundColor: '#ffffff',
                border: '2px solid #333', 
                boxShadow: '4px 4px 0px rgba(0,0,0,1)', 
                padding: '12px',
                borderRadius: '2px', 
                minWidth: '220px', 
                fontSize: '13px',
                marginTop: '10px'
              }}>
                <h3 style={{ 
                  margin: '0 0 8px 0', 
                  borderBottom: '2px solid #D32F2F', 
                  color: '#D32F2F', 
                  paddingBottom: '4px',
                  textTransform: 'uppercase',
                  fontSize: '15px'
                }}>
                  {selectedFire.props.satellite || 'SENSOR DATA'}
                </h3>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontWeight: 'bold', margin: '8px 0' }}>
                  <p style={{ margin: 0 }}>FRP: {selectedFire.props.frp ?? 'N/A'} MW</p>
                  <p style={{ margin: 0 }}>CONF: {selectedFire.props.confidence ?? 'N/A'}</p>
                </div>

                <div style={{ backgroundColor: '#f0f0f0', padding: '8px', marginTop: '10px', border: '1px solid #333' }}>
                  <p style={{ margin: '2px 0' }}><strong>Instrument:</strong> {selectedFire.props.instrument || 'N/A'}</p>
                  <p style={{ margin: '2px 0' }}><strong>Time:</strong> {selectedFire.props.acq_date} {selectedFire.props.acq_time}</p>
                  <p style={{ margin: '2px 0' }}><strong>Period:</strong> {selectedFire.props.daynight === 'D' ? '☀️ DAY' : '🌙 NIGHT'}</p>
                  {selectedFire.props.bright_ti4 && (
                    <p style={{ margin: '2px 0' }}><strong>Brightness:</strong> {selectedFire.props.bright_ti4} K</p>
                  )}
                </div>
              </div>
            </Popup>
          )}
        </Map>

        {hoverCoords && (
          <div style={{
            position: 'absolute', bottom: '20px', left: '20px', zIndex: 10,
            backgroundColor: '#ffffff', color: '#000', border: '2px solid #333',
            padding: '6px 12px', fontWeight: 'bold', fontFamily: 'monospace',
            boxShadow: '3px 3px 0px rgba(0,0,0,1)'
          }}>
            LNG: {hoverCoords.lng.toFixed(4)} | LAT: {hoverCoords.lat.toFixed(4)}
          </div>
        )}

        <div style={{ position: 'absolute', top: '20px', right: '20px', zIndex: 10, display: 'flex', gap: '10px' }}>
          <button onClick={() => setShowGrid(!showGrid)} style={{ 
            padding: '10px 15px', 
            background: showGrid ? '#333' : 'white', 
            color: showGrid ? 'white' : 'black',
            border: '2px solid #333',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 'bold',
            boxShadow: '2px 2px 0px rgba(0,0,0,1)'
          }}>
            GRID: {showGrid ? 'ON' : 'OFF'}
          </button>
          <button onClick={() => setIsGlobe(!isGlobe)} style={{ 
            padding: '10px 15px', 
            background: 'white', 
            color: 'black',
            border: '2px solid #333',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 'bold',
            boxShadow: '2px 2px 0px rgba(0,0,0,1)'
          }}>
            {isGlobe ? '2D MODE' : '3D MODE'}
          </button>
          {!isDashboardOpen && (
            <button onClick={() => setIsDashboardOpen(true)} style={{ 
              padding: '10px 15px', 
              background: '#333', 
              color: 'white',
              border: '2px solid #333',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 'bold',
              boxShadow: '2px 2px 0px rgba(0,0,0,1)'
            }}>
              OPEN DASHBOARD
            </button>
          )}
        </div>
      </div>

      <Dashboard
        isDashboardOpen={isDashboardOpen}
        setIsDashboardOpen={setIsDashboardOpen}
        showHotspots={showHotspots}
        setShowHotspots={setShowHotspots}
        showPerimeters={showPerimeters}
        setShowPerimeters={setShowPerimeters}
        visibleWildfires={visibleWildfires}
        wildfires={wildfires}
        loading={loading}
        debugMessage={debugMessage}
        queryPreview={queryPreview}
        flyToFire={flyToFire}
      />
    </div>
  );
}

export default App;