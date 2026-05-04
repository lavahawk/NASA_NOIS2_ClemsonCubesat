import React from 'react';
import type { FireProperties, FireCollection } from '../types';
import maplibregl from 'maplibre-gl';
import { getBboxForQuery } from '../utils';

interface DashboardProps {
  isDashboardOpen: boolean;
  setIsDashboardOpen: (open: boolean) => void;
  showHotspots: boolean;
  setShowHotspots: (show: boolean) => void;
  showPerimeters: boolean;
  setShowPerimeters: (show: boolean) => void;
  visibleWildfires: GeoJSON.Feature<GeoJSON.Geometry, FireProperties>[];
  visiblePerimeters: GeoJSON.Feature<GeoJSON.Geometry, FireProperties>[];
  wildfires: FireCollection;
  perimeters: FireCollection;
  loading: boolean;
  perimetersLoading: boolean;
  debugMessage: string;
  perimeterDebugMessage: string;
  queryPreview: { startTime: string; endTime: string; bbox: string };
  bounds: maplibregl.LngLatBounds | null;
  flyToFire: (lng: number, lat: number, props: FireProperties) => void;
  getFeatureCenter: (feature: GeoJSON.Feature<GeoJSON.Geometry, FireProperties>) => { lng: number; lat: number } | null;
  setSelectedFire: (fire: { lng: number; lat: number; props: FireProperties; geometryType?: string } | null) => void;
}

const Dashboard: React.FC<DashboardProps> = ({
  isDashboardOpen,
  setIsDashboardOpen,
  showHotspots,
  setShowHotspots,
  showPerimeters,
  setShowPerimeters,
  visibleWildfires,
  visiblePerimeters,
  wildfires,
  perimeters,
  loading,
  perimetersLoading,
  debugMessage,
  perimeterDebugMessage,
  queryPreview,
  bounds,
  flyToFire,
  getFeatureCenter,
  setSelectedFire,
}) => {
  if (!isDashboardOpen) {
    return null;
  }

  return (
    <aside style={{ width: '350px', padding: '20px', backgroundColor: '#f8f9fa', borderLeft: '1px solid #ccc', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
        <h2 style={{ margin: 0 }}>NOIS2 Tracker</h2>
        <button 
          onClick={() => setIsDashboardOpen(false)} 
          style={{ padding: '6px 12px', backgroundColor: 'black', color: 'white', borderRadius: '6px', cursor: 'pointer' }}
        >
          Exit ✖
        </button>
      </div>

      <div style={{ padding: '15px', backgroundColor: '#fff3e0', borderRadius: '10px', marginBottom: '20px', border: '2px solid #ff8c00' }}>
        <h4 style={{ margin: '0 0 10px 0', color: '#e65100', fontSize: '16px' }}>📡 Live API Params</h4>
        <div style={{ fontSize: '13px', fontFamily: 'monospace', lineHeight: '1.6' }}>
          <strong style={{ color: '#333' }}>BBOX:</strong><br />
          <span style={{ color: '#d32f2f' }}>{getBboxForQuery(bounds) || queryPreview.bbox}</span><br />
          <strong style={{ color: '#333' }}>Range:</strong><br />
          Previous 24h UTC
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
            cursor: 'pointer',
            transition: 'background-color 0.2s'
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
            cursor: 'pointer',
            transition: 'background-color 0.2s'
          }}
        >
          Perimeters: {showPerimeters ? 'ON' : 'OFF'}
        </button>
      </div>

      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: 'white', borderRadius: '8px', flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ margin: '0 0 10px 0' }}>Statistics</h3>
        <p style={{ fontWeight: 'bold' }}>
          Visible Hotspots: {loading ? 'Loading...' : visibleWildfires.length}
          <span style={{ fontWeight: 'normal', fontSize: '12px', marginLeft: '5px', color: '#6b7280' }}>
             (Total: {wildfires.features.length})
          </span>
        </p>
        <p style={{ fontWeight: 'bold' }}>
          Visible Perimeters: {perimetersLoading ? 'Loading...' : visiblePerimeters.length}
          <span style={{ fontWeight: 'normal', fontSize: '12px', marginLeft: '5px', color: '#6b7280' }}>
             (Total: {perimeters.features.length})
          </span>
        </p>
        <p style={{ fontSize: '12px', color: '#4b5563', marginTop: 0 }}>
          Debug: {debugMessage}
        </p>
        <p style={{ fontSize: '12px', color: '#4b5563', marginTop: 0 }}>
          Perimeters: {perimeterDebugMessage}
        </p>

        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {visibleWildfires.map((f: any, i: number) => {
            const center = getFeatureCenter(f);

            return (
              <div
                key={i}
                onClick={() => {
                  if (center) {
                    flyToFire(center.lng, center.lat, f.properties);
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
          {!perimetersLoading && visiblePerimeters.length > 0 && showPerimeters && (
            <>
              {visiblePerimeters.map((f: any, i: number) => {
                const center = getFeatureCenter(f);

                return (
                  <div
                    key={`perimeter-${i}`}
                    onClick={() => {
                      if (center) {
                        flyToFire(center.lng, center.lat, f.properties);
                        setSelectedFire({
                          lng: center.lng,
                          lat: center.lat,
                          props: f.properties ?? {},
                          geometryType: f.geometry?.type,
                        });
                      }
                    }}
                    style={{
                      padding: '10px',
                      backgroundColor: '#eef2ff',
                      border: '1px solid #c7d2fe',
                      borderRadius: '6px',
                      fontSize: '12px',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s, background-color 0.2s'
                    }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.borderColor = '#4d4dff';
                      e.currentTarget.style.backgroundColor = 'white';
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.borderColor = '#c7d2fe';
                      e.currentTarget.style.backgroundColor = '#eef2ff';
                    }}
                  >
                    <strong>Perimeter #{String(f?.properties?.id ?? i).substring(0, 8)}</strong>
                    <br />
                    Latest: <span style={{ color: '#3730a3', fontWeight: 'bold' }}>{f?.properties?.latest_detection_time ?? 'N/A'}</span>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>
    </aside>
  );
};

export default Dashboard;
