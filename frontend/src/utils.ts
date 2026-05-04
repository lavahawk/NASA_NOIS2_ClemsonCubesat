import type { FireProperties, FireCollection } from './types';
import { emptyFireCollection } from './types';
import maplibregl from 'maplibre-gl';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
export const DEFAULT_BBOX = '-179.2,18.9,-66.9,71.4';

export function formatLat(lat: number): string {
  if (lat === 0) return '0°';
  return `${Math.abs(lat)}°${lat > 0 ? 'N' : 'S'}`;
}

export function formatLng(lng: number): string {
  if (lng === 0) return '0°';
  return `${Math.abs(lng)}°${lng > 0 ? 'E' : 'W'}`;
}

export function buildLatLonGrid(step = 10) {
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

export function getPrevious24HoursQuery() {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  return { startTime: start.toISOString(), endTime: end.toISOString(), bbox: DEFAULT_BBOX };
}

export function normalizePointsResponse(data: any): FireCollection {
  const features = data?.features || data?.points?.features || data?.points || [];
  if (Array.isArray(features)) {
    return {
      type: 'FeatureCollection',
      features: features.map((f: any) => ({
        ...f,
        type: 'Feature'
      }))
    };
  }
  return emptyFireCollection;
}

export function normalizeFeatureCollection(data: any): FireCollection {
  const features = data?.features || data?.points?.features || data?.points || [];
  if (Array.isArray(features)) {
    return {
      type: 'FeatureCollection',
      features: features.map((f: any) => ({
        ...f,
        type: 'Feature'
      }))
    };
  }
  return emptyFireCollection;
}

export function getBboxForQuery(bounds: maplibregl.LngLatBounds | null): string {
  if (!bounds) return DEFAULT_BBOX;
  return [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ].join(',');
}

export function getFeatureCenter(feature: GeoJSON.Feature<GeoJSON.Geometry, FireProperties>) {
  const geometry = feature.geometry;
  if (!geometry) return null;

  if (geometry.type === 'Point') {
    const [lng, lat] = geometry.coordinates as [number, number];
    return { lng, lat };
  }

  if (geometry.type === 'Polygon') {
    const firstRing = geometry.coordinates?.[0];
    if (!firstRing?.length) return null;
    const [lng, lat] = firstRing[0] as [number, number];
    return { lng, lat };
  }

  if (geometry.type === 'MultiPolygon') {
    const firstRing = geometry.coordinates?.[0]?.[0];
    if (!firstRing?.length) return null;
    const [lng, lat] = firstRing[0] as [number, number];
    return { lng, lat };
  }

  return null;
}
