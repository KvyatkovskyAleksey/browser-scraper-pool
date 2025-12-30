from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "For list scrapers go to /scrapers, for health check go to /healthz"}

@app.get("/healthz")
async def healthz():
    """Function to check if the service is healthy."""
    return {"status": "ok"}

