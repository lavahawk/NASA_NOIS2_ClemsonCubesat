// tile math helpers

export const lonToTileX = (lon: number, z: number) =>
    Math.floor((lon + 180) / 360 * Math.pow(2, z));

export const latToTileY = (lat: number, z: number) =>
    Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, z));

export const tileToLon = (x: number, z: number) => (x / Math.pow(2, z)) * 360 - 180;

export const tileToLat = (y: number, z: number) => {
    const n = Math.PI - 2.0 * Math.PI * y / Math.pow(2, z);
    return 180.0 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
};

export const getTileBBox = (x: number, y: number, z: number) => ({
    minLon: tileToLon(x, z),
    minLat: tileToLat(y + 1, z),
    maxLon: tileToLon(x + 1, z),
    maxLat: tileToLat(y, z),
});
