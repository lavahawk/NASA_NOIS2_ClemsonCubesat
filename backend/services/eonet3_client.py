# Fetches officially named wildfire events
import requests
import pandas as pd
from datetime import datetime
from typing import Union, List, Literal, Tuple, Optional
from enum import Enum

class EoNet3Source:
    # Alaska & Canada
    AVO = "AVO"
    ABFIRE = "ABFIRE"
    BCWILDFIRE = "BCWILDFIRE"
    MBFIRE = "MBFIRE"

    # Australia
    AU_BOM = "AU_BOM"
    DFES_WA = "DFES_WA"

    # Antarctica / Ice
    BYU_ICE = "BYU_ICE"
    NATICE = "NATICE"

    # NASA Entities
    EO = "EO"
    EARTHDATA = "Earthdata"
    MRR = "MRR"
    NASA_ESRS = "NASA_ESRS"
    NASA_DISP = "NASA_DISP"
    NASA_HURR = "NASA_HURR"

    # NOAA & USGS
    NOAA_NHC = "NOAA_NHC"
    NOAA_CPC = "NOAA_CPC"
    USGS_EHP = "USGS_EHP"
    USGS_CMT = "USGS_CMT"
    HDDS = "HDDS"

    # International & Global
    CEMS = "CEMS"
    GDACS = "GDACS"
    GLIDE = "GLIDE"
    IDC = "IDC"
    JTWC = "JTWC"
    SIVOLCANO = "SIVolcano"

    # US Agencies & Reporting
    CALFIRE = "CALFIRE"
    FEMA = "FEMA"
    INCIWEB = "InciWeb"
    IRWIN = "IRWIN"
    PDC = "PDC"
    
    # News & Databases
    FLOODLIST = "FloodList"
    RELIEFWEB = "ReliefWeb"
    UNISYS = "UNISYS"

class EoNet3Category:
    DROUGHT = "drought"
    DUST_HAZE = "dustHaze"
    EARTHQUAKES = "earthquakes"
    FLOODS = "floods"
    LANDSLIDES = "landslides"
    MANMADE = "manmade"
    SEA_LAKE_ICE = "seaLakeIce"
    SEVERE_STORMS = "severeStorms"
    SNOW = "snow"
    TEMP_EXTREMES = "tempExtremes"
    VOLCANOES = "volcanoes"
    WATER_COLOR = "waterColor"
    WILDFIRES = "wildfires"

class EoNet3Magnitude:
    # Area Units
    ACRES = "ac"
    HECTARES = "ha"
    SQUARE_NAUTICAL_MILES = "sq_NM"
    
    # Wind
    AVG_MAX_WINDSPEED_KTS = "mag_kts"
    
    # Seismic Scales
    BODY_WAVE_MB = "mb"
    LOCAL_RICHTER_ML = "ml"
    MOMENT_MAGNITUDE_MMS = "mms"
    
    # Specific Seismic Inversions/Tensors
    BODY_WAVE_MWB = "mwb"
    CENTROID_MOMENT_TENSOR_MWC = "mwc"
    MOMENT_TENSOR_INVERSION_MWR = "mwr"
    
    # Waves
    # Assuming 'mi' is a specific P-wave magnitude from the API
    P_WAVE_MI = "mi"

class EoNet3Client:

    class Status(str, Enum):
        OPEN = 'open'
        CLOSED = 'closed'
        ALL = 'all'

    def __init__(self, base_url: str = 'https://eonet.gsfc.nasa.gov/api/v3'):
        self.base_url = base_url
        self.session = requests.Session()

    def events(
        self, 
        source: Optional[Union[str, List[str]]] = None, 
        category: Optional[Union[str, List[str]]] = None, 
        status: Status = Status.OPEN, 
        limit: Optional[int] = None,
        days: Optional[int] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        magID: Optional[str] = None,
        magMin: Optional[float] = None,
        magMax: Optional[float] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        geojson: bool = False
    ):
        
        # determine the url endpoint
        url = self.base_url + '/events'
        if (geojson == True):
            url += '/geojson'

        # set up the params
        params = {
            'source': ','.join(map(str, source)) if isinstance(source, list) else source,
            'category': ','.join(map(str, category)) if isinstance(category, list) else category,
            'status': status.value,
            'limit': limit,
            'days': days,
            'start': start.strftime('%Y-%m-%d') if isinstance(start, datetime) else start,
            'end': end.strftime('%Y-%m-%d') if isinstance(end, datetime) else end,
            'magID': magID,
            'magMin': magMin,
            'magMax': magMax,
            'bbox': ','.join(map(str, bbox)) if isinstance(bbox, tuple) else bbox
        }

        # clear empty parameters
        params = {k: v for k, v in params.items() if v is not None}

        # get response
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def categories(
        self,
        category: Optional[str] = None,
        source: Optional[Union[str, List[str]]] = None,
        status: Literal[Status.OPEN, Status.CLOSED] = Status.OPEN,
        limit: Optional[int] = None,
        days: Optional[int] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ):
        
        # url
        url = self.base_url + '/categories'
        if category:
            url += '/' + category

        # parameters
        params = {
            'source': ','.join(map(str, source)) if isinstance(source, list) else source,
            'status': status.value,
            'limit': limit,
            'days': days,
            'start': start.strftime('%Y-%m-%d') if isinstance(start, datetime) else start,
            'end': end.strftime('%Y-%m-%d') if isinstance(end, datetime) else end
        }

        # clear empty parameters
        params = {k: v for k, v in params.items() if v is not None}

        # get response
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def layers(
        self,
        category: Optional[str] = None
    ):
        
        # url
        url = self.base_url + '/layers'
        if category:
            url += '/' + category

        # get response
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

        

if __name__ == "__main__":
    bruh = EoNet3Client()
    #print(bruh.categories())
    #print(bruh.events(category=EoNet3Category.WILDFIRES))
    #print(bruh.layers())