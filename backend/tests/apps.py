# Interactive fromted dashboard

import streamlit as st
import pandas as pd
import requests

st.title("NASA Wildfire Tracker")
st.write("Live data powered by FastAPI")

API_URL =

try:
    response = requests.get(API_URL)
    
    # Verify if the API call was successful
    if response.status_code == 200:
        df = pd.DataFrame(response.json())
        
        st.subheader("Live Data from Backend")
        st.dataframe(df.head())
        
        st.subheader("Fire Hotspots Map")
        df = df.rename(columns={"latitude": "lat", "longitude": "lon"})
        st.map(df[["lat", "lon"]])
        
    else:
        st.error(f"Backend error occurred! Status code: {response.status_code}")

#Handle connection errors or other execptions
except requests.exceptions.ConnectionError:
    st.error("Server not found!")