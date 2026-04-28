import type { LayerProps } from 'react-map-gl/maplibre';

export const wildfireLayerStyle: LayerProps = {
  id: 'wildfires-point-layer',
  type: 'circle',
  filter: ['==', '$type', 'Point'],
  paint: {
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      2, ['interpolate', ['linear'], ['get', 'frp'], 0, 1, 100, 3, 500, 8],
      5, ['interpolate', ['linear'], ['get', 'frp'], 0, 2, 100, 5, 500, 12],
      8, ['interpolate', ['linear'], ['get', 'frp'], 0, 3, 100, 8, 500, 20]
    ],
    
    // High-saturation industrial color palette
    'circle-color': [
      'step',
      ['get', 'frp'],
      '#FFB300', // Low
      10, '#FF5722', // Moderate
      50, '#E64A19', // High
      100, '#D32F2F', // Severe
      300, '#8B0000'  // Catastrophic
    ],
    
    // Solid opacity so points don't look washed out
    'circle-opacity': 1.0, 
    
    // Dark outline toseparate the points from the light map background
    'circle-stroke-width': [
      'interpolate', ['linear'], ['zoom'],
      3, 0.5,
      8, 1.5
    ],
    'circle-stroke-color': '#2d2d2d', 
    'circle-stroke-opacity': 0.9
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