import { useEffect, useRef, useMemo } from 'react';
import maplibregl from 'maplibre-gl';

type MapHandler = (map: maplibregl.Map) => void;

export interface MapEvents {
    onLoad:      (fn: MapHandler) => void;
    onMoveEnd:   (fn: MapHandler) => void;
    offLoad:     (fn: MapHandler) => void;
    offMoveEnd:  (fn: MapHandler) => void;
}

// handler to hold callback functions for a map event
// order should not be assumed when registering events
export const useMapEvents = (map: maplibregl.Map | null) => {
    // use a set to ensure every callback is only registered once
    const loadHandlers = useRef<Set<MapHandler>>(new Set());
    const moveHandlers = useRef<Set<MapHandler>>(new Set());

    // update logic
    useEffect(() => {
        // no map nothing to do
        if (!map) return;

        // callback functions
        const onLoad = () => loadHandlers.current.forEach(fn => fn(map));
        const onMove = () => moveHandlers.current.forEach(fn => fn(map));

        // register with the map instance
        if (map.loaded()) {
            onLoad();
        } else {
            map.on('load', onLoad);
        }
        map.on('moveend', onMove);

        // clean up 
        return () => {
            map.off('load', onLoad);
            map.off('moveend', onMove);
        };
    }, [map]);

    // methods of the return object
    return useMemo(() => ({
        onLoad: (fn: MapHandler) => {
            loadHandlers.current.add(fn);
            if (map?.loaded()) fn(map);
        },
        onMoveEnd: (fn: MapHandler) => {
            moveHandlers.current.add(fn);
            if (map) fn(map);
        },
        offLoad: (fn: MapHandler) => loadHandlers.current.delete(fn),
        offMoveEnd: (fn: MapHandler) => moveHandlers.current.delete(fn),
    }), [map]);
};

/*
maby like use some existent fire through history and get the data from it
where to make the satellite "look" best determine where a spotfire is
receiving mid wave inferred images
*/