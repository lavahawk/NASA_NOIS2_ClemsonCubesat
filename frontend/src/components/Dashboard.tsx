import React from 'react';
import type { FireProperties, FireCollection } from '../types';

interface DashboardProps {
  isDashboardOpen: boolean;
  setIsDashboardOpen: (open: boolean) => void;
  showHotspots: boolean;
  setShowHotspots: (show: boolean) => void;
  showPerimeters: boolean;
  setShowPerimeters: (show: boolean) => void;
  visibleWildfires: GeoJSON.Feature<GeoJSON.Geometry, FireProperties>[];
  wildfires: FireCollection;
  loading: boolean;
  debugMessage: string;
  queryPreview: { startTime: string; endTime: string; bbox: string };
  flyToFire: (lng: number, lat: number, props: FireProperties) => void;
}

const Dashboard: React.FC<DashboardProps> = ({
  isDashboardOpen,
  setIsDashboardOpen,
  showHotspots,
  setShowHotspots,
  showPerimeters,
  setShowPerimeters,
  visibleWildfires,
  wildfires,
  loading,
  debugMessage,
  queryPreview,
  flyToFire,
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
          <span style={{ color: '#d32f2f' }}>{queryPreview.bbox}</span><br />
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
  );
};

export default Dashboard;
