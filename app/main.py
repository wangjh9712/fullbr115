from fastapi import FastAPI
from app.routers import meta

app = FastAPI(title="Fullbr115 API")

app.include_router(meta.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)