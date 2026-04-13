# Retrieves air quality and smoke concentration
import requests

class AqiClient:
    """A client to fetch current air quaility conditions for specfic coordinates using the Open-Meteo Air Quiality API."""
    
    def __init__(self, base_url: str = "https://air-quality-api.open-meteo.com/v1"):
        self.base_url = base_url
        self.session = requests.Session()

    def get(self, endpoint: str, params: dict = None) -> requests.Response:
        url = self.base_url + endpoint
        return self.session.get(url, params=params)

    def get_smoke_data(self, lat: float, lon: float) -> dict:
       
        """Fetches the current smoke indicators (PM2.5 and carbon monoxide) for a specific coordinate."""
        params = {
            "latitude": lat,
            "longitude": lon,
            # pm 2.5 is a key indicator of smoke pollution, while carbon monoxide can also be elevated during wildfires
            "current": "pm10,pm2_5,carbon_monoxide", 
            "timezone": "auto"
        }
        
        try:
            response = self.get('/air-quality', params=params)
            response.raise_for_status()
            data = response.json()
            
            current = data.get('current', {})
            return {
                "lat": lat,
                "lon": lon,
                "pm2_5_ugm3": current.get('pm2_5'),
                "carbon_monoxide_ugm3": current.get('carbon_monoxide')
            }
        except Exception as e:
            print(f"AQI Air Quality Fetch Error: {e}")
            return {}