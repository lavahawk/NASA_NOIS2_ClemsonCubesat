from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from services.eonet3_client import EoNet3Client, EoNet3Category

app = FastAPI(title="NASA EONET Wildfire API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = EoNet3Client()

@app.get("/wildfires")
async def get_wildfires(
    status: EoNet3Client.Status = Query(EoNet3Client.Status.OPEN, description="Status of the events (open, closed, all)"),
    days: Optional[int] = Query(None, description="Number of days to look back"),
    limit: Optional[int] = Query(None, description="Maximum number of events to return")
):
    """
    Fetches wildfire events from NASA's EONET API in GeoJSON format.
    """
    data = client.events(
        category=EoNet3Category.WILDFIRES,
        status=status,
        days=days,
        limit=limit,
        geojson=True
    )
    return data

@app.get("/")
async def root():
    return {"message": "Welcome to the NASA EONET Wildfire API. Visit /docs for documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
