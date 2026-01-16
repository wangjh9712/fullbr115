from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routers import meta
from app.routers import resources
from app.routers import p115

app = FastAPI(title="Fullbr115")

app.include_router(meta.router)
app.include_router(resources.router)
app.include_router(p115.router)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)