import requests
import pandas as pd

class GfwClient:
    """
    Client for fetching live fire alerts from Global Forest Watch (GFW).
    Requires a free API key from the GFW Developer Portal.
    """
    def __init__(self, api_key: str, base_url: str = "https://data-api.globalforestwatch.org"):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": self.api_key})

    def get(self, endpoint: str, params: dict = None) -> requests.Response:
        url = self.base_url + endpoint
        return self.session.get(url, params=params)

    def get_fire_alerts_by_bbox(self, min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> pd.DataFrame:
        # Increased LIMIT from 500 to 10000 for global scale
        sql = f"""
            SELECT latitude, longitude, alert__date, confidence__cat, alert__time_utc 
            FROM data 
            WHERE latitude >= {min_lat} AND latitude <= {max_lat} 
            AND longitude >= {min_lon} AND longitude <= {max_lon}
            ORDER BY alert__date DESC 
            LIMIT 10000
        """
        
        try:
            response = self.get('/dataset/nasa_viirs_fire_alerts/latest/query', params={"sql": sql})
            response.raise_for_status()
            
            data = response.json().get('data', [])
            
            if not data:
                return pd.DataFrame()
                
            df = pd.DataFrame(data)
            
            df = df.rename(columns={
                'alert__date': 'date',
                'confidence__cat': 'confidence',
                'alert__time_utc': 'time_utc'
            })
            return df
            
        except Exception as e:
            print(f"GFW API Error: {e}")
            return pd.DataFrame()

# Test Execution Block
if __name__ == "__main__":
    print("Starting Global Forest Watch API setup...")
    
    YOUR_GFW_API_KEY = "dd7dbd5d-0f70-422f-b45d-00cc87ce120a"
    
    if YOUR_GFW_API_KEY == "PUT_YOUR_API_KEY_HERE":
        print("Waiting for API key. Please follow the instructions to get one!")
    else:
        print("API Key detected. Fetching global data...")
        client = GfwClient(api_key=YOUR_GFW_API_KEY)
        
        # Coordinates cover the entire globe
        min_lat, min_lon = -90.0, -180.0
        max_lat, max_lon = 90.0, 180.0
        
        df = client.get_fire_alerts_by_bbox(min_lat, min_lon, max_lat, max_lon)
        
        if not df.empty:
            print(f"\nGlobal Fetch Success! {len(df)} fire alerts retrieved")
            print("\n--- DataFrame Preview ---")
            print(df.head())
        else:
            print("\nNo fires found, or the query failed.")