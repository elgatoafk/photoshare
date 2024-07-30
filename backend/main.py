import sys
import os
import uvicorn
import logging
from fastapi import FastAPI
from backend.src.routes import auth, user, photo, comment, tag, rating, root
from backend.src.util.db import Base, async_engine
from backend.src.config.config import settings
from fastapi.middleware.cors import CORSMiddleware

from backend.src.routes import transformations

# Ensure correct PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..')

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION
)

# CORS Middleware setup, adjust as necessary
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Database initialization

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Include API routers
app.include_router(root.router, prefix="", tags=["root"])
app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(user.router, prefix="", tags=["users"])
app.include_router(photo.router, prefix="", tags=["photos"])
app.include_router(comment.router, prefix="", tags=["comments"])
app.include_router(tag.router, prefix="", tags=["tags"])
app.include_router(rating.router, prefix="", tags=["ratings"])
app.include_router(transformations.router, prefix="", tags=["transformations"])


@app.on_event("startup")
async def on_startup():
    await init_db()


# Run the application
if __name__ == "__main__":
    debug_mode = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=debug_mode)
