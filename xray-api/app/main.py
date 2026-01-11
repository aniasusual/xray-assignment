"""
X-Ray API Main Application

FastAPI application for receiving and querying X-Ray traces.

Reference: IMPLEMENTATION_PLAN.md -> "API Backend"
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .config import settings
from .database import init_db
from .routers import ingest, query

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ingest.router, prefix="/api", tags=["Ingest"])
app.include_router(query.router, prefix="/api", tags=["Query"])


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting X-Ray API...")
    logger.info(f"Database URL: {settings.database_url}")

    # Create tables if they don't exist
    init_db()

    logger.info("✅ X-Ray API started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down X-Ray API...")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "healthy"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,  # Hot reload during development
    )
