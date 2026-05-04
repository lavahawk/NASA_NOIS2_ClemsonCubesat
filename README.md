# NASA NOIS-2 Wildfire Tracker

An end-to-end geospatial system for real-time monitoring of wildfire hotspots and perimeters across North America. This project ingests high-resolution VIIRS detection data from NASA FIRMS, processes it into deduplicated records and generated fire perimeters, and visualizes the results on an interactive 2D/3D dashboard.

## Key Features

- **Real-time Ingestion:** Background worker polls NASA FIRMS every 5 minutes for the latest VIIRS (SNPP, NOAA-20, NOAA-21) detections.
- **Smart Deduplication:** Deterministic `source_key` generation ensures that overlapping polling cycles do not create duplicate records.
- **Automated Perimeter Generation:** Uses DBSCAN clustering and PostGIS spatial operations (`ST_ConcaveHull`, `ST_Buffer`) to generate and update fire perimeters as new hotspots are detected.
- **Geospatial API:** High-performance FastAPI service serving GeoJSON points and polygons with support for spatial (BBOX) and temporal filtering.
- **Interactive Dashboard:** Modern React + Vite frontend with MapLibre GL for fluid 2D/3D map visualization, including live API parameter monitoring and fire statistics.
- **Extensible Data Sources:** Built-in (but independent) clients for Google Earth Engine Dynamic World (land cover) and GridMET (meteorological data) for advanced analysis.

## Architecture

### Backend
- **Background Worker:** A Python process responsible for data ingestion, normalization, and perimeter calculation.
- **FastAPI Service:** Serves the processed data via a RESTful API.
- **PostGIS (PostgreSQL 17):** The central geospatial database storing hotspot points and perimeter polygons.

### Frontend
- **React + TypeScript + Vite:** A responsive web application.
- **MapLibre GL / React Map GL:** Handles 2D/3D map rendering and interactive layers.
- **GeoJSON Integration:** Consumes standard geospatial formats directly from the API.

## Getting Started

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- A NASA FIRMS [Map Key](https://firms.modaps.eosdis.nasa.gov/api/config/).

### Setup & Run
1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd NASA_NOIS2_ClemsonCubesat
    ```

2.  **Configure environment variables:**
    Copy the example environment file and add your NASA FIRMS key.
    ```powershell
    # Windows
    copy .env.example .env
    # Linux/macOS
    cp .env.example .env
    ```
    Edit `.env` and set `FIRMS_MAP_KEY=your_key_here`.

3.  **Start the entire stack:**
    ```bash
    docker compose up --build
    ```

4.  **Access the application:**
    - **Frontend:** [http://localhost:5173](http://localhost:5173)
    - **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

## API Endpoints

- `GET /v1/points`: Retrieves wildfire hotspot points.
  - Params: `start_time`, `end_time`, `bbox` (required), `cursor` (pagination), and various filters (FRP, confidence, satellite).
- `GET /v1/perimeters`: Retrieves generated fire perimeters as polygons.
  - Params: `start_time`, `end_time`, `bbox`.

## Project Structure

- `/backend`: Python source code for the worker, API, and data clients.
  - `/api_service`: FastAPI implementation.
  - `/background_worker`: Ingestion and perimeter logic.
  - `/firms`: NASA FIRMS client.
  - `/sources/dynamic_world`: Google Earth Engine land cover client.
  - `/sources/gridmet`: Meteorological data client.
  - `/migrations`: SQL schema definitions.
- `/frontend`: React application source code.
  - `/src/components`: UI components like the Dashboard.
  - `/src/hooks`: Custom React hooks for data fetching.
- `docker-compose.yml`: Infrastructure orchestration.

## Development

### Running Backend Locally (without Docker)
1. Install dependencies: `pip install -r backend/requirements.txt`
2. Run Worker: `python backend/run_background_worker.py`
3. Run API: `python backend/run_fast_api.py`

### Running Frontend Locally
1. Navigate to `/frontend`: `cd frontend`
2. Install dependencies: `npm install`
3. Start dev server: `npm run dev`

---
*Developed for NASA NOIS-2 by the Clemson Cubesat Team.*
