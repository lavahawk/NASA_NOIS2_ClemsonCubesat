# Manual fetching of NASA fire data using the FirmsClient and saving it to a CSV file for Streamlit to read.

from firms_client import FirmsClient
import pandas as pd
from datetime import datetime

# SETUP
MY_KEY = "" 
client = FirmsClient(api_key = MY_KEY)
print("Testing NASA Earthdata connection...")

try:
    # Verify API Key validity and check remaining quota
    status = client.mapkey_status()
    remaining = client.transaction_remaining()
    print(f"API Status Check: {remaining} transactions remaining today.")

    # DATA FETCHING
    # Testing: Calls the .area() method in firms_client.py
    today = datetime.now().strftime('%Y-%m-%d')
    california_bbox = '-124.48,32.53,-114.13,42.01'
    
    print(f"Fetching latest fire data for California...")
    df = client.area(
        source='VIIRS_SNPP_NRT',
        date=today, 
        day_range=1,
        area=california_bbox
    )

    # Verify and save the data
    if not df.empty:
        print(f"Success! Fetched {len(df)} fire hotspots.")
        print(df.head()) # Display first few rows for the meeting
        
        # Save to CSV (Task 3.2 algorithm will read this file) 
        df.to_csv("nasa_fire_data.csv", index=False)
        print("Data saved to 'nasa_fire_data.csv'.")
    else:
        print("Connection successful, but no active fires detected in this area today.")


except Exception as e:
    print(f"Error: {e}")
    print("Check if you have 'requests' and 'pandas' installed in your venv.")