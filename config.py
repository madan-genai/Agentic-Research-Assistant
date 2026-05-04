from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All configurable values for the Agentic Research Assistant.
    Pydantic reads these from environment variables or the .env file.

    Fields without a default value (e.g. gemini_api_key) are REQUIRED.
    The server will refuse to start if they are missing.

    Fields with a default value (e.g. tavily_api_key: str = "") are optional.
    """
    # ── Required API keys ─────────────────────────────────────────────────────
    gemini_api_key: str
    
    # ── Optional API keys ─────────────────────────────────────────────────────
    tavily_api_key: str = ""
    
    qdrant_url: str = ""
    # Empty string = no knowledge base. The kb_search node skips gracefully.

    qdrant_api_key: str = ""
    qdrant_collection: str = "research-agent"

    # ── LLM settings ─────────────────────────────────────────────────────────
    llm_model: str = "gemini-2.5-flash"
    
    # ── Database settings ─────────────────────────────────────────────────────
    db_path: str = "research_history.db"
    

    # ── Server settings ───────────────────────────────────────────────────────
    port: int = 8002

    # ── Pydantic config ───────────────────────────────────────────────────────
    model_config = {
        "env_file": ".env",            # Read from .env file in the working directory
        "env_file_encoding": "utf-8",
        "extra": "ignore",             
    }
settings = Settings()
