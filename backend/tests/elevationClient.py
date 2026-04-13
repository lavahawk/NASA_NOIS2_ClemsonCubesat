#Know how much the fire accelerates when moving uphill
import requests

class ElevationClient:
    """
    Fetches elevation data for specific coordinates using the Open-Meteo Elevation API.
    """
    
    def __init__(self, base_url: str = "https://api.open-meteo.com/v1"):
        self.base_url = base_url
        self.session = requests.Session()

    def get(self, endpoint: str, params: dict = None) -> requests.Response:
        url = self.base_url + endpoint
        return self.session.get(url, params=params)

    def get_elevation(self, lat: float, lon: float) -> dict:
        """Fetches elevation data for a specific coordinate."""
        params = {
            "latitude": lat,
            "longitude": lon
        }
        
        try:
            response = self.get('/elevation', params=params)
            response.raise_for_status()
            data = response.json()
            
            # Open-Meteo Elevation API return elevation in a list, we take the first value
            elevations = data.get('elevation', [0.0])
            elevation_m = elevations[0] if elevations else 0.0
            
            return {
                "lat": lat,
                "lon": lon,
                "elevation_meters": elevation_m
            }
        except Exception as e:
            print(f"Elevation fetch error: {e}")
            return {}

if __name__ == "__main__":
    print("Starting elevation data fetch...")
    client = ElevationClient()
    
    # HARRISON Wildfire coordinates (example)
    test_lat = 36.568752
    test_lon = -96.849207
    
    print(f"Measuring the elevation at coordinates({test_lat}, {test_lon})...")
    elevation_data = client.get_elevation(test_lat, test_lon)
    
    if elevation_data:
        alt = elevation_data.get('elevation_meters')
        print(f"\n Success! The elevation at the wildfire site is: {alt} meters")
        
        if alt > 1500:
            print(" This is a high-altitude wildfire. Thin air and steep terrain make firefighting extremely difficult!")
        else:
            print("This wildfire is located in a plain or low-elevation hilly area.")
    else:
        print("\nFailed to fetch elevation data. Please check your internet connection.")