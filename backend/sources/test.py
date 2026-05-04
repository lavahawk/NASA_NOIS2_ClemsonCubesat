import dynamic_world as dw
import ee
from google.oauth2 import service_account
from dynamic_world import DynamicWorldClient
from datetime import datetime

credentials = service_account.Credentials.from_service_account_file(
    "citric-snow-441001-k0-e76261507a92.json",
    scopes=["https://www.googleapis.com/auth/earthengine"],
)

  
client = dw.DynamicWorldClient(credentials=credentials, project="citric-snow-441001-k0")

result = client.get_land_cover(when="2025-04-20", latitude=45, longitude=-100, max_days_distance=30)
print(result)