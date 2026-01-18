from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routers import meta, resources, p115, subscription
from app.services.subscription import subscription_service
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(subscription_service.start_scheduler())
    yield
    task.cancel()

app = FastAPI(title="Fullbr115")

app.include_router(meta.router)
app.include_router(resources.router)
app.include_router(p115.router)
app.include_router(subscription.router)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)