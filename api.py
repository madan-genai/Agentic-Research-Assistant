import asyncio
import os
import json
import logging

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from agent import ResearchState, build_agent
from config import settings
from database import save_report, delete_report, get_report, list_reports
from model import DeleteResponse, HistoryItem, HistoryListReport, ResearchRequest

logger = logging.getLogger(__name__)

app_state: dict = {}

NODE_DISPLAY = {
    "validate_topic": "Validating research topic",
    "analyze_query": "Analyzing research topic",
    "decide_search_strategy": "Planning search strategy",
    "web_search": "Searching the web",
    "kb_search": "Searching knowledge base",
    "synthesize": "Writing research report",
}


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def research(request: ResearchRequest):
    if "agent" not in app_state:
        raise HTTPException(status_code=503, detail="agent not ready")

    agent = app_state["agent"]

    initial_state = ResearchState(
        topic=request.topic,
        override_web_search=request.web_search,
        is_valid=False,
        Validation_reason="",
        sub_questions=[],
        search_strategy="",
        web_results=[],
        vector_results=[],
        report="",
        sources=[],
        thinking_steps=[],
    )

    async def event_generator():
        try:
            yield sse_event({
                "event": "start",
                "message": f"Starting research on {request.topic}",
            })

            final_report = ""
            final_sources = []
            final_sub_questions = []
            final_strategy = "web_only"
            final_is_valid = True
            final_validation_reason = ""
            final_vector_results = []

            async for chunk in agent.astream(initial_state, stream_mode="updates"):
                for node_name, output in chunk.items():
                    if node_name not in NODE_DISPLAY:
                        continue

                    yield sse_event({
                        "event": "node_start",
                        "node": node_name,
                        "display": NODE_DISPLAY[node_name],
                        "message": f"{NODE_DISPLAY[node_name]}...",
                    })

                    await asyncio.sleep(0.05)

                    steps = output.get("thinking_steps", [])
                    for step in steps:
                        yield sse_event({
                            "event": "thinking",
                            "node": node_name,
                            "message": step,
                        })
                        await asyncio.sleep(0.08)

                    if node_name == "synthesize":
                        final_report = output.get("report", "")
                        final_sources = output.get("sources", [])

                    if node_name == "analyze_query":
                        final_sub_questions = output.get("sub_questions", [])
                        final_strategy = output.get("search_strategy", "web_only")

                    if node_name == "validate_topic":
                        final_is_valid = output.get("is_valid", True)
                        final_validation_reason = output.get("validation_reason", "")

                    if node_name == "kb_search":
                        final_vector_results = output.get("vector_results", [])

            if not final_is_valid:
                yield sse_event({
                    "event": "error",
                    "message": f"Invalid research topic: {final_validation_reason}",
                })

            elif final_report:
                report_id = save_report(
                    topic=request.topic,
                    report_md=final_report,
                    sources=final_sources,
                    sub_questions=final_sub_questions,
                )

                yield sse_event({
                    "event": "complete",
                    "report": final_report,
                    "sub_questions": final_sub_questions,
                    "sources": final_sources,
                    "report_id": report_id,
                })

                yield sse_event({
                    "event": "summary",
                    "state": {
                        "topic": request.topic,
                        "sub_questions": final_sub_questions,
                        "urls_searched": len(final_sources),
                        "kb_searched": bool(final_vector_results),
                        "strategy": final_strategy,
                    },
                })

            else:
                yield sse_event({
                    "event": "error",
                    "message": "Report generation failed",
                })

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            yield sse_event({"event": "error", "message": str(e)})

        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def get_history():
    reports = list_reports()
    return HistoryListReport(
        reports=[HistoryItem(**r) for r in reports],
        total=len(reports),
    )


def get_history_report(report_id: str):
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def download_pdf(report_id: str):
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    from pdf_generator import generate_pdf

    try:
        pdf_bytes = generate_pdf(
            topic=report["topic"],
            report_md=report["report_md"],
            sources=report["sources"],
        )
    except Exception as e:
        logger.error(f"PDF error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="PDF generation failed")

    safe_topic = "".join(c if c.isalnum() or c in " _-" else "_" for c in report["topic"])
    safe_topic = safe_topic[:40].strip()
    filename = f"research_{safe_topic}_{report_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def delete_history_report(report_id: str):
    deleted = delete_report(report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Report not found")
    return deleted


def health():
    return {
        "status": "ok",
        "agent_ready": "agent" in app_state,
        "qdrant_configured": bool(settings.qdrant_url),
    }
