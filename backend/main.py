import sys
import os
import uvicorn
from fastapi import FastAPI
from backend.src.routes import auth, user, photo, comment, rating, root
from backend.src.util.db import Base, async_engine
from backend.src.config.config import settings
from fastapi.middleware.cors import CORSMiddleware

# Ensure correct PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..')

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
)

# CORS Middleware setup, adjust as necessary
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

# Include API routers
app.include_router(root.router, prefix="", tags=["root"])
app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(user.router, prefix="", tags=["users"])
app.include_router(photo.router, prefix="", tags=["photos"])
app.include_router(comment.router, prefix="", tags=["comments"])
app.include_router(rating.router, prefix="", tags=["ratings"])

@app.on_event("startup")
async def on_startup():
    await init_db()

# Run the application
if __name__ == "__main__":
    debug_mode = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    uvicorn.run(app, host="127.0.0.1", port=8080, reload=debug_mode)
