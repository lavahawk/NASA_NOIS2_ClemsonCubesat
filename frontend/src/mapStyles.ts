import type { LayerProps } from 'react-map-gl/maplibre';

export const wildfireLayerStyle: LayerProps = {
  id: 'wildfires-point-layer',
  type: 'circle',
  filter: ['==', '$type', 'Point'],
  paint: {
    // Exaggerate the size difference so the worst fires are massively larger
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      2, ['interpolate', ['linear'], ['get', 'frp'], 0, 1, 100, 3, 500, 8],
      5, ['interpolate', ['linear'], ['get', 'frp'], 0, 2, 100, 5, 500, 12],
      8, ['interpolate', ['linear'], ['get', 'frp'], 0, 3, 100, 8, 500, 20]
    ],
    
    // Stark contrast palette: Muted yellows -> Reds -> Neon Magenta -> White Hot
    'circle-color': [
      'step',
      ['get', 'frp'],
      '#ffcc00', // 0-10: Muted Gold (Low - blends in)
      10, '#f38d8dea', // 10-50: Moderate 
      50, '#d75151', // 50-100: High
      100, '#a10d12', // 100-300: Severe - instantly catches the eye
      300, '#610404'  // >300: Catastrophic - impossible to miss
    ],
    
    // Make small fires transparent so the big ones punch through the clusters
    'circle-opacity': [
      'interpolate', ['linear'], ['get', 'frp'],
      0, 0.4,    // Low intensity is very see-through
      50, 0.8,   // High intensity is mostly solid
      100, 1.0   // Severe intensity is 100% solid
    ],
    
    // Only give the worst fires a border so they pop out
    'circle-stroke-width': [
      'step', ['get', 'frp'],
      0,       // No border for FRP < 50
      50, 1.5, // 1.5px border for FRP > 50
      100, 2   // 2px border for the absolute worst ones
    ],
    
    // A dark outline for the White-Hot fires, and a white outline for everything else
    'circle-stroke-color': [
      'step', ['get', 'frp'],
      '#ffffff', 
      300, '#000000' // Give the white-hot fires a harsh black border
    ],
  },
};

export const wildfirePolygonLayerStyle: LayerProps = {
  id: 'wildfires-polygon-layer',
  type: 'fill',
  filter: ['==', '$type', 'Polygon'],
  paint: {
    'fill-color': '#4d4dff',
    'fill-opacity': 0.4,
  },
};

export const wildfirePolygonOutlineStyle: LayerProps = {
  id: 'wildfires-polygon-outline',
  type: 'line',
  filter: ['==', '$type', 'Polygon'],
  paint: {
    'line-color': '#4d4dff',
    'line-width': 2,
  },
};

export const gridLineStyle: LayerProps = {
  id: 'latlon-grid-lines',
  type: 'line',
  paint: {
    'line-color': '#f87923',
    'line-width': 1.2,
    'line-opacity': 0.85,
  },
};

export const gridLabelStyle: LayerProps = {
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
    'text-color': '#f87923',
    'text-halo-color': '#ffffff',
    'text-halo-width': 2,
  },
};