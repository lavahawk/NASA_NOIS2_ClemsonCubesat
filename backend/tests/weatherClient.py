# Retrieves real-time wind speed and temperature
import requests
import pandas as pd

class WeatherClient:
    """A client to fetch current weather conditions for specific coordinates using the Open-Meteo API."""
    
    def __init__(self, base_url: str = "https://api.open-meteo.com/v1"):
        self.base_url = base_url
        self.session = requests.Session()

    def get(self, endpoint: str, params: dict = None) -> requests.Response:
        url = self.base_url + endpoint
        return self.session.get(url, params=params)

    def get_fire_weather(self, lat: float, lon: float) -> dict:
        
        """Fetches current weather conditions (wind speed, temperature, humidity)."""
        
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "ms", # (m/s)
            "timezone": "auto"
        }
        
        try:
            response = self.get('/forecast', params=params)
            response.raise_for_status()
            data = response.json()
            
            current = data.get('current', {})
            return {
                "lat": lat,
                "lon": lon,
                "temp_c": current.get('temperature_2m'),
                "humidity_percent": current.get('relative_humidity_2m'),
                "wind_speed_ms": current.get('wind_speed_10m'),
                "wind_direction_deg": current.get('wind_direction_10m')
            }
        except Exception as e:
            print(f"Weather fetch error: {e}")
            return {}