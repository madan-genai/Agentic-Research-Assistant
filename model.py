from typing import List , Optional
from pydantic import BaseModel

class ResearchRequest(BaseModel):
    """
    The body of POST /research.
    The user sends a topic; optionally forces web search on/off.
    """
    topic : str 
    web_search : Optional[bool] = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"topic": "Impact of large language models on education"},
                {"topic": "Latest advances in quantum computing 2025", "use_web_search": True},
            ]
        }
    }

class Source(BaseModel):
    """
    A source of information, either from web search or knowledge base.
    """
    title: str
    url: Optional[str] = None
    content : str

class ResearchReport(BaseModel):
    """
    The body of GET /research/{id}.
    The full research report, including all sources.
    """
    topic: str
    report_md: str           # Full markdown report text
    sources: List[Source]
    search_strategy: str     # "web_only" or "both"
    sub_questions: List[str] # The 3 sub-questions the agent generated
    url_count: int
    created_at: str

class HistoryItem(BaseModel):
    """
    A summary row shown in the history list.

    We deliberately do NOT include the full report text here —
    it can be large. The history list only shows enough info to
    identify and choose a report. Full text is fetched on demand.
    """
    id : str
    topic : str
    url_count : int
    created_at : str

class HistoryListReport(BaseModel):
    """
    The body of GET /history.
    A list of past research reports, with summary info for each.
    Returned by GET /history
    """
    reports : List[HistoryItem]
    total : int

class DeleteResponse(BaseModel):
    """
    Returned by DELETE /history/{id}.
    """
    status : str
    id : str
