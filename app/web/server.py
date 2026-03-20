from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.storage.database import StorageService
from app.config import settings
import os

app = FastAPI(title="Bitget XAUUSD Dashboard")
storage = StorageService()

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/api/status")
async def get_status():
    status = storage.get_status("current_state")
    if not status:
        return {"msg": "No state found. Bot might not be running."}
    return status

@app.get("/api/trades")
async def get_trades():
    return storage.get_recent_trades(50, mode=settings.RUN_MODE)

@app.get("/api/equity")
async def get_equity():
    return storage.get_equity_curve(mode=settings.RUN_MODE)

def run_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
