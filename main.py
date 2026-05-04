import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent import build_agent
from api import (
    app_state,
    research,
    get_history,
    get_history_report,
    download_pdf,
    delete_history_report,
    health,
)
from config import settings
from database import init_db
from model import DeleteResponse, ResearchRequest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the agent at startup."""
    logger.info("Initializing research agent...")
    try:
        agent = build_agent(settings.gemini_api_key)
        app_state["agent"] = agent
        logger.info("Agent initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise

    # Initialize database
    init_db()

    yield

    # Cleanup if needed
    logger.info("Shutting down...")


app = FastAPI(
    title="Research Agent API",
    description="An agentic research assistant that generates reports from web and knowledge base sources.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/research")
async def research_endpoint(request: ResearchRequest):
    """Start a research task and stream the progress."""
    return await research(request)


@app.get("/history")
def history_endpoint():
    """Get the list of all research reports."""
    return get_history()


@app.get("/history/{report_id}")
def history_report_endpoint(report_id: str):
    """Get a specific research report by ID."""
    return get_history_report(report_id)


@app.get("/history/{report_id}/pdf")
def download_pdf_endpoint(report_id: str):
    """Download a research report as PDF."""
    return download_pdf(report_id)


@app.delete("/history/{report_id}", response_model=DeleteResponse)
def delete_history_report_endpoint(report_id: str):
    """Delete a research report by ID."""
    return delete_history_report(report_id)


@app.get("/health")
def health_endpoint():
    """Health check endpoint."""
    return health()