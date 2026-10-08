import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile

from .models import ScreeningReport
from .pipeline import screen

app = FastAPI(title="Resume Screener")
_last_report: ScreeningReport | None = None


@app.post("/screen", response_model=ScreeningReport, response_model_exclude_none=True)
async def screen_resumes(files: list[UploadFile]) -> ScreeningReport:
    global _last_report
    with tempfile.TemporaryDirectory() as tmp:
        for upload in files:
            name = Path(upload.filename or "resume").name
            (Path(tmp) / name).write_bytes(await upload.read())
        _last_report = await screen(Path(tmp))
    return _last_report


@app.get("/results", response_model=ScreeningReport, response_model_exclude_none=True)
async def results() -> ScreeningReport:
    if _last_report is None:
        raise HTTPException(status_code=404, detail="No screening run yet; POST /screen first")
    return _last_report
