# "Single-run test script" used to test the NASA API connection and manually save the fetched data as a CSV file.

import streamlit as st
import pandas as pd
import requests

# Title of the app
st.title("NASA Wildfire Tracker")
df = pd.read_csv("nasa_fire_data.csv") 

# Raw data display
st.subheader("Raw Data")
st.dataframe(df.head())

# Auto-generated map of fire hotspots
st.subheader("Fire Hotspots Map")
df = df.rename(columns={
    "latitude": "lat",
    "longitude": "lon"
})
st.map(df[["lat", "lon"]])