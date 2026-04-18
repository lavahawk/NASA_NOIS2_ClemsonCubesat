import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import type { MapEvents } from './useMapEvents';

const SOURCE_ID = 'perimeter-data';
const FILL_LAYER_ID = 'perimeter-fill-layer';
const LINE_LAYER_ID = 'perimeter-line-layer';

export const usePerimeters = (
    mapEvents: MapEvents,
    enabled: boolean
) => {
    useEffect(() => {
        const clearData = (map: maplibregl.Map) => {
            const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
            if (source) {
                source.setData({ type: 'FeatureCollection', features: [] });
            }
        };

        if (!enabled) {
            mapEvents.onLoad(clearData);
            return () => {
                mapEvents.offLoad(clearData);
            };
        }

        const fetchData = async (map: maplibregl.Map) => {
            if (!enabled) return;

            const bounds = map.getBounds();
            const minLon = bounds.getWest();
            const minLat = bounds.getSouth();
            const maxLon = bounds.getEast();
            const maxLat = bounds.getNorth();

            const url = `http://localhost:8000/perimeters?min_lon=${minLon}&min_lat=${minLat}&max_lon=${maxLon}&max_lat=${maxLat}`;
            
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error('Failed to fetch perimeters');
                const geojson = await response.json();

                if (!map.getSource(SOURCE_ID)) {
                    map.addSource(SOURCE_ID, {
                        type: 'geojson',
                        data: geojson
                    });
                    
                    // Add fill layer
                    map.addLayer({
                        id: FILL_LAYER_ID,
                        type: 'fill',
                        source: SOURCE_ID,
                        paint: {
                            'fill-color': '#ff4d4d',
                            'fill-opacity': 0.3
                        }
                    });

                    // Add outline layer
                    map.addLayer({
                        id: LINE_LAYER_ID,
                        type: 'line',
                        source: SOURCE_ID,
                        paint: {
                            'line-color': '#ff4d4d',
                            'line-width': 2
                        }
                    });
                } else {
                    const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
                    source.setData(geojson);
                }
            } catch (error) {
                console.error('Error fetching perimeters:', error);
            }
        };

        mapEvents.onLoad(fetchData);
        mapEvents.onMoveEnd(fetchData);

        return () => {
            mapEvents.offLoad(fetchData);
            mapEvents.offMoveEnd(fetchData);
        };
    }, [enabled, mapEvents]);
};
