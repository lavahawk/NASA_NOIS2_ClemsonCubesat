import requests
import pandas as pd

class FirmsClient:
    def __init__(self, api_key: str, base_url: str = "https://firms.modaps.eosdis.nasa.gov"):
        self.base_url = base_url
        self.session = requests.Session()
        self.api_key = api_key

    def get(self, endpoint: str) -> requests.Response:
        """
        Queries the FIRMS api for a given endpoint.

        Args:
            endpoint: the endpoint to query
        
        Returns:
            the response from the query
        """
        url = self.base_url + endpoint
        return self.session.get(url)
    
    def read_csv(self, endpoint: str) -> pd.DataFrame:
        """
        Queries the FIRMS api for a csv endpoint

        Args:
            endpoint: the endpoint to query
        
        Returns:
            the response from the query
        """

        url = self.base_url + endpoint
        return pd.read_csv(url)

    def mapkey_status(self):
        """
        Queries the status of the API KEY.

        Returns: 
            Dictionary: {
                'transaction_limit': int,
                'current_transactions': int,
                'transaction_interval': string
            }

        """

        try:
            response = self.get('/mapserver/mapkey_status/?MAP_KEY=' + self.api_key)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException, ValueError:
            return {
                'transaction_limit': 0, 
                'current_transactions': 0, 
                'transaction_interval': '0'
            }
        
    def transaction_limit(self) -> int:
        """
        Returns:
            the max calls to the api in the given interval.
        """
        return self.mapkey_status()['transaction_limit']
    
    def transaction_count(self) -> int:
        """
        Returns:
            the current count of api calls in the given interval
        """
        return self.mapkey_status()['current_transactions']
    
    def transaction_remaining(self) -> int:
        """
        Returns:
            the number of remaining transactions in the interval
        """
        return self.transaction_limit() - self.transaction_count()
    
    def ok(self) -> bool:
        """
        Returns:
            true if the client is in a usable state
        """
        return self.transaction_limit() > 0
    
    def availability(self, source: str = 'all') -> pd.DataFrame:
        """
        gets the availability of satellite sensors

        Args:
            source: The satellite/sensor name to check. Defaults to all
        
        Returns:
            The DataFrame with columns: data_id, min_date, max_date
        """
        return self.read_csv('/api/data_availability/csv/' + self.api_key + '/' + source)

    def area(self, source: str, date: str, day_range: int, area: str = 'world') -> pd.DataFrame:
        """
        Fetches the fire hotspot data for a given area

        Args:
            source: The satellite/sensor to search (e.g. 'MODIS_NRT', 'VIIRS_NOAA20_NRT').
            date: The date corresponding to the most recent data element. Must be YYYY-MM-DD format
            day_range: The number of days to look backwards (data - day_range - 1 = total query amount)
            area: The area to search. Can be an entire region 'world', 'north', 'south'
                  or specific coordinates 'x1,y1,x2,y2' with max boundaries -180, -90, 180, 90

        """
        endpoint = f'/api/area/csv/{self.api_key}/{source}/{area}/{day_range}/{date}'
        return self.read_csv(endpoint)