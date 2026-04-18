import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import type { MapEvents } from './useMapEvents';
import { lonToTileX, latToTileY, getTileBBox } from '../utils/tileUtils';

const SOURCE_ID = 'viirs-data';
const LAYER_ID = 'viirs-layer';

export interface BBox {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
}

export const useVIIRS = (
    mapEvents: MapEvents,
    color: string,
    startTime: string,
    endTime: string,
    enabled: boolean
) => {
    const fetchedTiles = useRef<Set<string>>(new Set());
    const allFeatures = useRef<GeoJSON.Feature[]>([]);

    useEffect(() => {
        let active = true;

        // Clear cache if parameters change
        fetchedTiles.current.clear();
        allFeatures.current = [];
        
        const clearData = (map: maplibregl.Map) => {
            const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
            if (source) {
                source.setData({ type: 'FeatureCollection', features: [] });
            }
        };

        const updateLayerColor = (map: maplibregl.Map) => {
            if (map.getLayer(LAYER_ID)) {
                map.setPaintProperty(LAYER_ID, 'circle-color', color);
            }
        };

        const fetchData = async (map: maplibregl.Map) => {
            if (!enabled || !active) return;

            const bounds = map.getBounds();
            const z = Math.floor(map.getZoom());
            const minX = lonToTileX(bounds.getWest(), z);
            const maxX = lonToTileX(bounds.getEast(), z);
            const minY = latToTileY(bounds.getNorth(), z);
            const maxY = latToTileY(bounds.getSouth(), z);

            const newTiles: {x: number, y: number, z: number, key: string}[] = [];
            for (let x = minX; x <= maxX; x++) {
                for (let y = minY; y <= maxY; y++) {
                    const key = `${z}/${x}/${y}/${startTime}/${endTime}`;
                    if (!fetchedTiles.current.has(key)) {
                        newTiles.push({x, y, z, key});
                    }
                }
            }

            if (newTiles.length === 0) return;

            // Mark as fetched immediately to avoid duplicate requests
            newTiles.forEach(t => fetchedTiles.current.add(t.key));

            const fetchPromises = newTiles.map(async (tile) => {
                const bbox = getTileBBox(tile.x, tile.y, tile.z);
                const url = `http://localhost:8000/viirs?min_lon=${bbox.minLon}&min_lat=${bbox.minLat}&max_lon=${bbox.maxLon}&max_lat=${bbox.maxLat}&start_time=${startTime}&end_time=${endTime}`;
                
                try {
                    const response = await fetch(url);
                    if (!response.ok) throw new Error(`Failed to fetch VIIRS data for tile ${tile.key}`);
                    const data = await response.json() as GeoJSON.FeatureCollection;
                    return data.features;
                } catch (error) {
                    console.error(error);
                    if (active) {
                        fetchedTiles.current.delete(tile.key); // Allow retry
                    }
                    return [];
                }
            });

            const results = await Promise.all(fetchPromises);
            if (!active) return;

            const flatResults = results.flat();
            if (flatResults.length === 0) return;
            
            allFeatures.current.push(...flatResults);
            
            const geojson: GeoJSON.FeatureCollection = {
                type: 'FeatureCollection',
                features: allFeatures.current
            };

            const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
            if (!source) {
                map.addSource(SOURCE_ID, {
                    type: 'geojson',
                    data: geojson
                });
                map.addLayer({
                    id: LAYER_ID,
                    type: 'circle',
                    source: SOURCE_ID,
                    paint: {
                        'circle-radius': 5,
                        'circle-color': color,
                        'circle-stroke-width': 1,
                        'circle-stroke-color': '#ffffff'
                    }
                });
            } else {
                source.setData(geojson);
                updateLayerColor(map);
            }
        };

        // Initial clear and fetch/update
        mapEvents.onLoad(clearData);
        if (enabled && startTime && endTime) {
            mapEvents.onLoad(fetchData);
            mapEvents.onMoveEnd(fetchData);
        }

        return () => {
            active = false;
            mapEvents.offLoad(clearData);
            mapEvents.offLoad(fetchData);
            mapEvents.offMoveEnd(fetchData);
        };
    }, [enabled, mapEvents, color, startTime, endTime]);
};
