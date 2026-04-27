export type FireProperties = {
  id?: string | number;
  frp?: number;
  confidence?: number | string;
  satellite?: string;
  acq_date?: string;
  acq_time?: string;
  daynight?: string;
  instrument?: string;
  bright_ti4?: number;
  bright_ti5?: number;
  version?: string;
  scan?: number;
  track?: number;
  $type?: string;
  [key: string]: any;
};

export type FireCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, FireProperties>;

export const emptyFireCollection: FireCollection = {
  type: 'FeatureCollection',
  features: [],
};