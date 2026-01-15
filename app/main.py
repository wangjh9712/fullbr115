from fastapi import FastAPI
from app.routers import meta
from app.routers import resources
from app.routers import p115

app = FastAPI(title="Fullbr115 API")

app.include_router(meta.router)
app.include_router(resources.router)
app.include_router(p115.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)