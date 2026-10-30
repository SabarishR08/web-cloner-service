import os
import shutil
import uuid
import asyncio
import urllib.parse
from typing import Dict
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from cloner_engine import WebsiteCloner

app = FastAPI(title="WebCloner Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp_jobs")
os.makedirs(TEMP_DIR, exist_ok=True)

# Jobs state store in memory
# job_id -> { "url": str, "status": "running"|"completed"|"failed", "logs": [], "queue": asyncio.Queue(), "zip_path": str, "site_name": str }
jobs: Dict[str, dict] = {}

class CloneRequest(BaseModel):
    url: str
    max_pages: int = 5

def clean_old_jobs():
    """Simple cleanup for folders older than 1 hour or when jobs exceed limit"""
    try:
        if len(jobs) > 50:
            for jid in list(jobs.keys())[:20]:
                job_data = jobs.pop(jid, None)
                if job_data and "job_dir" in job_data and os.path.exists(job_data["job_dir"]):
                    shutil.rmtree(job_data["job_dir"], ignore_errors=True)
    except Exception:
        pass

def run_cloner_task(job_id: str, url: str, max_pages: int, loop: asyncio.AbstractEventLoop):
    job = jobs[job_id]
    job_dir = job["job_dir"]
    output_dir = os.path.join(job_dir, "site")
    zip_path = os.path.join(job_dir, "cloned_website.zip")
    job["zip_path"] = zip_path

    def notify(msg: str):
        job["logs"].append(msg)
        asyncio.run_coroutine_threadsafe(job["queue"].put({"log": msg, "status": "running"}), loop)

    try:
        notify(f"🚀 Initializing crawler for: {url}")
        cloner = WebsiteCloner(
            base_url=url,
            output_dir=output_dir,
            max_pages=max_pages,
            log_callback=notify
        )
        cloner.run(zip_path)
        job["status"] = "completed"
        notify("🎉 Website cloning complete and ZIP ready for download!")
        asyncio.run_coroutine_threadsafe(job["queue"].put({"status": "completed", "log": "Done"}), loop)
    except Exception as e:
        job["status"] = "failed"
        err_msg = str(e)
        notify(f"❌ Error encountered: {err_msg}")
        asyncio.run_coroutine_threadsafe(job["queue"].put({"status": "failed", "error": err_msg}), loop)

@app.post("/api/clone")
async def start_clone(req: CloneRequest, background_tasks: BackgroundTasks):
    raw_url = req.url.strip()
    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        raw_url = "https://" + raw_url

    parsed = urllib.parse.urlparse(raw_url)
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL provided")

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(TEMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    domain_name = parsed.netloc.replace(":", "_")

    jobs[job_id] = {
        "url": raw_url,
        "site_name": domain_name,
        "status": "running",
        "logs": [],
        "queue": asyncio.Queue(),
        "job_dir": job_dir,
        "zip_path": None
    }

    clean_old_jobs()

    loop = asyncio.get_running_loop()
    background_tasks.add_task(run_cloner_task, job_id, raw_url, req.max_pages, loop)

    return {"job_id": job_id, "url": raw_url, "status": "started"}

@app.get("/api/progress/{job_id}")
async def stream_progress(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    async def event_generator():
        # Yield existing logs first
        for log in job["logs"]:
            import json
            yield f"data: {json.dumps({'log': log, 'status': job['status']})}\n\n"

        if job["status"] in ("completed", "failed"):
            import json
            yield f"data: {json.dumps({'status': job['status']})}\n\n"
            return

        while True:
            try:
                # Wait for next event
                data = await asyncio.wait_for(job["queue"].get(), timeout=30.0)
                import json
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("status") in ("completed", "failed"):
                    break
            except asyncio.TimeoutError:
                # Keep-alive heartbeat
                yield ": ping\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/download/{job_id}")
async def download_zip(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    zip_path = job.get("zip_path")

    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=400, detail="ZIP file is not ready or failed to generate")

    filename = f"{job['site_name']}_clone.zip"
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename
    )

# Static files mount
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>WebCloner API is running</h1>"

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
