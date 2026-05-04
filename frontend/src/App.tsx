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
  normalizeFeatureCollection,
  getBboxForQuery,
  getFeatureCenter,
} from './utils';
import Dashboard from './components/Dashboard';

function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const activePointsFetchIdRef = useRef(0);
  const activePerimetersFetchIdRef = useRef(0);

  const [wildfires, setWildfires] = useState<FireCollection>(emptyFireCollection);
  const [perimeters, setPerimeters] = useState<FireCollection>(emptyFireCollection);
  const [loading, setLoading] = useState(false);
  const [perimetersLoading, setPerimetersLoading] = useState(false);
  const [bounds, setBounds] = useState<maplibregl.LngLatBounds | null>(null);

  const [showHotspots, setShowHotspots] = useState(true);
  const [showPerimeters, setShowPerimeters] = useState(true);
  const [isDashboardOpen, setIsDashboardOpen] = useState(true);
  const [isGlobe, setIsGlobe] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom] = useState(4);
  const [hoverCoords, setHoverCoords] = useState<{ lng: number; lat: number } | null>(null);
  const [selectedFire, setSelectedFire] = useState<{ lng: number; lat: number; props: FireProperties; geometryType?: string } | null>(null);
  const [debugMessage, setDebugMessage] = useState('No points loaded yet');
  const [perimeterDebugMessage, setPerimeterDebugMessage] = useState('No perimeters loaded yet');
  const queryPreview = useMemo(() => getPrevious24HoursQuery(), []);

  const flyToFire = useCallback((lng: number, lat: number, props: FireProperties) => {
    if (!mapRef.current) return;
    mapRef.current.flyTo({ center: [lng, lat], zoom: 12, essential: true, duration: 2000 });
    setSelectedFire({ lng, lat, props });
  }, []);

  const fetchNASAData = useCallback(async () => {
    const fetchId = activePointsFetchIdRef.current + 1;
    activePointsFetchIdRef.current = fetchId;
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
        if (activePointsFetchIdRef.current !== fetchId) return;

        setDebugMessage(`Loaded ${allFeatures.length} points across ${pageCount} page(s)`);
        setWildfires({ type: 'FeatureCollection', features: [...allFeatures] });

        hasMore = Boolean(data?.has_more);
        nextCursor = typeof data?.next_cursor === 'string' ? data.next_cursor : null;
      }
    } catch (err) {
      if (activePointsFetchIdRef.current === fetchId) {
        setDebugMessage(err instanceof Error ? err.message : 'API query failed');
      }
    } finally {
      if (activePointsFetchIdRef.current === fetchId) setLoading(false);
    }
  }, []);

  const fetchPerimeterData = useCallback(async () => {
    const fetchId = activePerimetersFetchIdRef.current + 1;
    activePerimetersFetchIdRef.current = fetchId;
    setPerimetersLoading(true);
    setPerimeterDebugMessage('Querying /v1/perimeters...');

    const query = getPrevious24HoursQuery();
    const params = new URLSearchParams({
      start_time: query.startTime,
      end_time: query.endTime,
      bbox: getBboxForQuery(bounds),
    });

    try {
      const response = await fetch(`${API_BASE_URL}/v1/perimeters?${params.toString()}`);
      if (!response.ok) throw new Error(`Perimeter API Connection Failed: ${response.status}`);

      const data = await response.json();
      const collection = normalizeFeatureCollection(data);
      if (activePerimetersFetchIdRef.current !== fetchId) return;

      setPerimeters(collection);
      setPerimeterDebugMessage(`Loaded ${collection.features.length} perimeter(s) from /v1/perimeters`);
    } catch (err) {
      if (activePerimetersFetchIdRef.current === fetchId) {
        setPerimeterDebugMessage(err instanceof Error ? err.message : 'Perimeter API query failed');
        setPerimeters(emptyFireCollection);
      }
    } finally {
      if (activePerimetersFetchIdRef.current === fetchId) setPerimetersLoading(false);
    }
  }, [bounds]);

  useEffect(() => {
    fetchNASAData();
  }, [fetchNASAData]);

  useEffect(() => {
    fetchPerimeterData();
  }, [fetchPerimeterData]);

  useEffect(() => {
    if (!selectedFire) return;
    const isPolygon = selectedFire.geometryType === 'Polygon' || selectedFire.geometryType === 'MultiPolygon';
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

  const visiblePerimeters = useMemo(() => {
    if (!perimeters.features.length) return [];
    return perimeters.features;
  }, [perimeters]);

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
        geometryType: feature.geometry?.type,
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
          interactiveLayerIds={['wildfires-point-layer', 'wildfires-polygon-layer', 'wildfires-polygon-outline']}
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

          {perimeters.features.length > 0 && showPerimeters && (
            <Source id="wildfires-polygon-data" type="geojson" data={perimeters}>
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
                <h3 style={{ margin: 0 }}>
                  {selectedFire.geometryType === 'Polygon' || selectedFire.geometryType === 'MultiPolygon'
                    ? 'Fire Perimeter'
                    : selectedFire.props.satellite || 'Satellite Point'}
                </h3>
                <p><strong>ID:</strong> {selectedFire.props.id ?? 'N/A'}</p>
                {(selectedFire.geometryType === 'Polygon' || selectedFire.geometryType === 'MultiPolygon') ? (
                  <>
                    <p><strong>Latest Detection:</strong> {selectedFire.props.latest_detection_time ?? 'N/A'}</p>
                    <p><strong>Detections:</strong> {selectedFire.props.detection_count ?? 'N/A'}</p>
                  </>
                ) : (
                  <>
                    <p><strong>FRP:</strong> {selectedFire.props.frp ?? 'N/A'} MW</p>
                    <p><strong>Conf:</strong> {selectedFire.props.confidence ?? 'N/A'}</p>
                  </>
                )}
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

      <Dashboard
        isDashboardOpen={isDashboardOpen}
        setIsDashboardOpen={setIsDashboardOpen}
        showHotspots={showHotspots}
        setShowHotspots={setShowHotspots}
        showPerimeters={showPerimeters}
        setShowPerimeters={setShowPerimeters}
        visibleWildfires={visibleWildfires}
        visiblePerimeters={visiblePerimeters}
        wildfires={wildfires}
        perimeters={perimeters}
        loading={loading}
        perimetersLoading={perimetersLoading}
        debugMessage={debugMessage}
        perimeterDebugMessage={perimeterDebugMessage}
        queryPreview={queryPreview}
        bounds={bounds}
        flyToFire={flyToFire}
        getFeatureCenter={getFeatureCenter}
        setSelectedFire={setSelectedFire}
      />
    </div>
  );
}

export default App;
