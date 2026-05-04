import logging
import os
from operator import add
from typing import Annotated, List, Optional

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict
from dotenv import load_dotenv

load_dotenv()

MAX_URLS = 25

logger = logging.getLogger(__name__)

class TopicValidation(BaseModel):
    """
    The LLM evaluates whether a topic is worth researching.
    This prevents the agent from burning API calls on gibberish or empty input.
    """
    is_valid: bool
    """True if this is a meaningful topic that a researcher could write about."""

    reason: str
    """One sentence explaining why the topic is valid or invalid."""

    refined_topic: str
    """
    If valid: a cleaned-up version of the topic (fix typos, add context).
    If invalid: return the original topic unchanged.
    """

class QueryAnalysis(BaseModel):
    """LLM fills this in to plan the research strategy."""

    sub_questions: List[str]
    """Exactly 3 focused sub-questions that together cover the topic."""

    search_strategy: str
    """
    One of: 'web_only' | 'both'.
    Use 'both' when the topic would benefit from both web results
    AND any locally indexed documents.
    """

    reasoning: str
    """Brief explanation of why this strategy was chosen."""
     
     

class ResearchState(TypedDict):
    #Input from user
    topic : str
    override_web_search : Optional[bool]

    # Validation Step
    is_valid : bool
    Validation_reason : str

    # Planning Step (set by analyze_query node)
    sub_questions : list[str]
    search_strategy : str

    # Search results
    web_results = list[dict]
    vector_results = list[dict]

    # Output
    report : str
    sources : list[dict]

    thinking_steps : Annotated[list[str], add]

def build_agent(gemini_api_key: str):
    """
    Build and compile the LangGraph research agent.

    This function is called ONCE at server startup (in main.py's lifespan).
    The compiled agent is stored in app_state and reused for every request —
    same pattern as how Lecture 18/19 reuse the LLM and embeddings.

    Args:
        gemini_api_key — passed in from the environment, not hardcoded here.

    Returns:
        A compiled LangGraph graph ready to call .astream_events() on.
    """

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7, api_key=gemini_api_key)

    validation_llm = llm.with_structured_output(TopicValidation)
    analysis_llm = llm.with_structured_output(QueryAnalysis)

    tavily_api_key = os.getenv("TAVILY_API_KEY", "")


    def validate_topic(state: ResearchState) -> dict:
        """
        Ask the LLM whether this is a meaningful research topic.
        If invalid, the graph will stop here (conditional edge routes to END).
        """
        topic = state["topic"]
        logger.info(f"Validating topic: {topic!r}")
        prompt = f"""
You are a strict research topic validator and refiner.

Your task is to evaluate whether the given topic is suitable for a 2-page academic or professional report.

## Evaluation Criteria

A topic is VALID if:
- It is understandable and not gibberish
- It has a clear subject or intent
- It can reasonably be expanded into explanation, analysis, or research
- It contains enough context (not overly vague or single generic word)

A topic is INVALID if:
- It is meaningless, random, or nonsensical (e.g., "asdfgh", "123xyz")
- It is too vague (e.g., "things", "stuff", "hello")
- It is empty or whitespace
- It is broken or incomplete
- It is offensive, harmful, or inappropriate

## Instructions

1. Decide if the topic is valid (true/false)
2. Provide EXACTLY ONE concise sentence explaining your decision
3. If valid:
   - Refine the topic by fixing grammar, spelling, and clarity
   - Make it slightly more specific if needed
   - Preserve original intent (do NOT change meaning)
4. If invalid:
   - Return the topic EXACTLY as provided (no modification)

## Strict Output Rules

- Output MUST be valid JSON
- Do NOT include any extra text
- Do NOT include explanations beyond one sentence
- Do NOT hallucinate meaning for invalid input
- If uncertain → mark as INVALID

## Output Schema

{{
  "is_valid": boolean,
  "reason": string,
  "refined_topic": string
}}

## Topic
"{topic}"
"""
        result = validation_llm.invoke([HumanMessage(content=prompt)])
        if result.is_valid:
            steps = [
                f'Checking topic: "{topic}"',
                f"✓ Valid research topic — {result.reason}",
            ]
            if result.refined_topic and result.refined_topic != topic:
                steps.append(f'Refined to: "{result.refined_topic}"')
            # Use the refined topic if the LLM cleaned it up
            refined = result.refined_topic if result.refined_topic else topic
        else:
            steps = [
                f'Checking topic: "{topic}"',
                f"✗ Invalid topic — {result.reason}",
            ]
            refined = topic  # Keep original even if invalid

        return {
            "is_valid": result.is_valid,
            "validation_reason": result.reason,
            "topic": refined,          # May be refined/corrected
            "thinking_steps": steps,   # Reducer appends these to the list
        }
    
    
    def analyze_query(state: ResearchState) -> dict:
        """
        LLM plans how to research this topic by breaking it down into sub-questions
        and choosing a search strategy.
        """
        topic = state["topic"]
        override = state.get("override_web_search")
        logger.info(f"Analyzing topic: {topic!r}")
        prompt = f"""
You are a research query planner.

Your task is to decompose a topic into focused research questions and select an appropriate search strategy.

## Topic
"{topic}"

## Objectives

1. Generate EXACTLY 3 sub-questions:
   - Each must be specific, clear, and independently searchable
   - Together, they must comprehensively cover the topic
   - Avoid overlap or redundancy
   - Avoid vague phrasing like "discuss" or "explain generally"

2. Select a search strategy:

   - "web_only":
     Use when the topic requires:
     • recent developments
     • current statistics
     • news or time-sensitive data

   - "both":
     Use when the topic:
     • is academic, historical, or conceptual
     • benefits from stable knowledge + external updates
     • may exist in a local knowledge base

## Reasoning

Provide a SHORT explanation (1-2 sentences) for why the chosen strategy is appropriate.

## Strict Rules

- Output MUST be valid JSON
- Generate EXACTLY 3 sub-questions (no more, no less)
- Sub-questions must NOT repeat the topic verbatim
- Do NOT include extra text outside JSON
- Be concise and precise
- Do NOT hallucinate unnecessary complexity

## Output Schema

{{
  "sub_questions": [string, string, string],
  "search_strategy": "web_only" | "both",
  "reasoning": string
}}
"""
        analysis = analysis_llm.invoke([HumanMessage(content=prompt)])

        strategy = analysis.search_strategy
        if override is True:
            strategy = "web_only"
        steps = [
            f"Strategy chosen: {strategy}",
            f"Reason: {analysis.reasoning}",
            "Breaking topic into 3 focused sub-questions:",
            f"  Q1: {analysis.sub_questions[0]}",
            f"  Q2: {analysis.sub_questions[1]}",
            f"  Q3: {analysis.sub_questions[2]}",
        ]

        return {
            "sub_questions": analysis.sub_questions,
            "search_strategy": strategy,
            "thinking_steps": steps,
        }
    
    def decide_search_strategy(state: ResearchState) -> dict:
        """Log the search strategy. Routing is done by the conditional edge."""
        strategy = state.get("search_strategy", "web_only")
        return {
            "thinking_steps": [
                f"Search plan confirmed: {strategy}",
                f"Will search {len(state.get('sub_questions', []))} sub-question(s) — max {MAX_URLS} URLs total",
            ]
        }
    

    def web_search(state: ResearchState) -> dict:
        """
        Search Tavily for each sub-question, collecting up to MAX_URLS results total.

        KEY CHANGE vs original: we now log the EXACT query string and URL count
        per sub-question so students can see exactly what goes to the internet.
        """
        sub_questions = state.get("sub_questions", [])
        all_results = []
        steps = [f"Starting web search - cap {MAX_URLS} URLS total"]
        for i, question in enumerate(sub_questions, 1):
            # Stop early if we've already hit the URL cap
            if len(all_results) >= MAX_URLS:
                steps.append(f"Reached max URL limit of {MAX_URLS}, stopping search")
                break

            # Calculate how many results to request for this sub-question
            remaining = MAX_URLS - len(all_results)
            per_query = min(7, remaining)

            steps.append(f"Searcching for Query{i}/{len(sub_questions)}: \"{question}\"")

            try:
                tavily = TavilySearchResults(
                    max_results=per_query,
                    tavily_api_key=tavily_api_key
                )
                results = tavily.run(question)

                if isinstance(results,list) and results:
                    all_results.extend(results)
                    steps.append(f"   ↳ {len(results)} URL(s) found (total so far: {len(all_results)})")
                    for r in results[:3]:   # Show first 3 titles for transparency
                        title = r.get("title", "")[:60]
                        steps.append(f"     • {title}")
                    if len(results) > 3:
                        steps.append(f"     • ... and {len(results) - 3} more")
                else:
                    steps.append("   ↳ No results returned for this query")

            except Exception as e:
                logger.warning(f"Tavily search failed for '{question}': {e}")
                steps.append(f"   ↳ Search failed: {str(e)[:80]}")

        steps.append(f"Web search complete — {len(all_results)} URL(s) collected")
        return {"web_results": all_results, "thinking_steps": steps}

    
    def Kb_search(state: ResearchState) -> dict:
        """
        Search the Qdrant knowledge base for relevant chunks.
        Skips gracefully if QDRANT_URL is not set in the environment.
        """
        qdrant_url = os.getenv("QDRANT_URL","")
        if not qdrant_url:
            return {
                "vector_results": [],
                "thinking_steps": ["No Qdrant URL configured, skipping vector search"]
            }
        
        topic = state["topic"]
        steps = ["Searching local knowledge base for relevant information..."]
        try: 
            from langchain_huggingface import HuggingFaceEmbeddings
            from qdrant_client import QdrantClient

            qdrant_api_key = os.getenv("QDRANT_API_KEY","")
            collection_name = os.getenv("QDRANT_COLLECTION","research_agent")

            embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
            steps.append(f"Embedding query for vector search: \"{topic[:60]}\"")

            query_vector = embeddings.embed_query(topic)
            client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            results = client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=MAX_URLS,
                with_payload=True,
                with_vectors=False, 
            )

            chunks = []
            for chunk in results.points:
                chunk_text = chunk.point.payload.get("chunk_text"," ")
                if chunk_text:
                    chunks.append(chunk_text)
            steps.append(f"Vector search complete — {len(chunks)} relevant chunk(s) found")
            return {"vector_results": chunks, "thinking_steps": steps}
        except ImportError:
            steps.append("Knowledge base packages not installed, skipping")
            return {"vector_results": [], "thinking_steps": steps}
        except Exception as e:
            logger.warning(f"KB search failed: {e}")
            steps.append(f"Knowledge base search failed: {str(e)[:80]}")
            return {"vector_results": [], "thinking_steps": steps}
    
    def synthesize(state: ResearchState) -> dict:
        """
        Combine all research findings into a detailed structured report.
        """
        topic = state["topic"]
        web_results = state.get("web_results", [])
        vector_results = state.get("vector_results", [])

        steps = [
            f"Combining {len(web_results)} web source(s) + {len(vector_results)} KB chunk(s)",
            "Drafting report structure: Executive Summary → Background → Findings → Analysis → Conclusion",
        ]

        # ── Build context string from web results ─────────────────────────────
        context_parts = []
        sources = []

        for result in web_results:
            content = result.get("content", "")[:600]   # Limit each snippet to 600 chars
            url = result.get("url", "")
            title = result.get("title", url)

            if content:
                context_parts.append(f"[Web Source: {title}]\n{content}")

            if url:
                sources.append({
                    "title": title,
                    "url": url,
                    "content_preview": content[:120] + "..." if len(content) > 120 else content,
                })

        # ── Add knowledge base chunks if any ─────────────────────────────────
        for chunk in vector_results:
            context_parts.append(f"[Knowledge Base]\n{chunk}")

        # Combine all context, separated by dividers for clarity
        context = "\n\n---\n\n".join(context_parts) if context_parts else "No external sources found."

        # Build a numbered source list for the report footer
        source_list = "\n".join(
            f"{i+1}. {s['title']}\n   {s['url']}"
            for i, s in enumerate(sources)
        ) if sources else "No web sources were found."

        steps.append("Sending context to LLM for synthesis...")

        # ── Generate the report via LLM ───────────────────────────────────────
        # ChatPromptTemplate lets us keep the prompt readable as a template
        # with {placeholder} variables filled in at invoke() time.
        report_prompt = ChatPromptTemplate.from_template("""
You are a senior research analyst specializing in evidence-based reporting and synthesis.

Your task is to generate a structured, high-quality research report using ONLY the provided sources.

---

## Topic
{topic}

---

## Source Material
{context}

---

## Instructions

- Use ONLY the provided context. Do NOT introduce external knowledge.
- If information is missing, explicitly state: "Insufficient data available."
- Prioritize:
  1. Recent and specific information
  2. Consistency across multiple sources
- If sources conflict:
  - Acknowledge the disagreement
  - Provide a reasoned interpretation
- Cite sources inline using: (Source: <title>)
- Maintain analytical, precise, and formal tone

---

## Required Output Structure

# {topic}

## Executive Summary
- Concise synthesis of key findings
- Highlight most critical insights

## Background & Context
- Define the topic clearly
- Provide relevant historical or conceptual context

## Current State & Key Findings
- Present verified facts from sources
- Include multiple perspectives where available
- Use inline citations

## Analysis & Implications
- Interpret the findings
- Identify trends, risks, and opportunities
- Avoid speculation beyond evidence

## Conclusion
- Summarize key takeaways
- Provide actionable or strategic insights

## Sources
{source_list}

---

## Quality Constraints

- Minimum 3 sentences per section
- Avoid redundancy
- Prefer specificity over generalization
- Do NOT hallucinate facts
"""
        )
        

        # LCEL chain: prompt → LLM → parse output as a plain string
        chain = report_prompt | llm | StrOutputParser()
        report = chain.invoke({
            "topic": topic,
            "context": context,
            "source_list": source_list,
        })

        steps.append("✓ Report generation complete")

        return {
            "report": report,
            "sources": sources,
            "thinking_steps": steps,
        }


    # ── Routing functions ─────────────────────────────────────────────────────
    # These are NOT nodes — they are functions that tell LangGraph which
    # node to go to next. They inspect the state and return a string
    # that matches one of the keys in the conditional edge map.

    def route_after_validation(state: ResearchState) -> str:
        """
        After validate_topic:
          - If topic is valid → continue to analyze_query
          - If topic is invalid → END the graph (error will be handled by api.py)
        """
        if state.get("is_valid", False):
            return "analyze_query"
        return "__end__"   # Special LangGraph key to route to END

    def route_search(state: ResearchState) -> str:
        """
        After decide_search_strategy:
          Always go to web_search first. kb_search runs after web_search
          for ALL strategies (it skips itself if Qdrant is not configured).
        """
        # We always do web search. kb_search runs next and self-skips if not needed.
        return "web_search"


    # ── Build the graph ───────────────────────────────────────────────────────
    # StateGraph takes our state TypedDict as its schema.
    # Nodes are added with add_node(name, function).
    # Edges define the flow between nodes.

    workflow = StateGraph(ResearchState)

    # ── Add all nodes ─────────────────────────────────────────────────────────
    workflow.add_node("validate_topic", validate_topic)
    workflow.add_node("analyze_query", analyze_query)
    workflow.add_node("decide_search_strategy", decide_search_strategy)
    workflow.add_node("web_search", web_search)
    workflow.add_node("kb_search", Kb_search)
    workflow.add_node("synthesize", synthesize)

    # ── Set entry point ───────────────────────────────────────────────────────
    # Every request starts at validate_topic (our first node)
    workflow.set_entry_point("validate_topic")

    # ── Add edges ─────────────────────────────────────────────────────────────
    # add_conditional_edges(from_node, routing_fn, route_map)
    # The routing_fn returns a string; route_map maps strings to target nodes.

    # After validation: valid → analyze, invalid → END
    workflow.add_conditional_edges(
        "validate_topic",
        route_after_validation,
        {
            "analyze_query": "analyze_query",
            "__end__": END,
        },
    )

    # analyze_query → decide_search_strategy (always)
    workflow.add_edge("analyze_query", "decide_search_strategy")

    # decide_search_strategy → web_search (always, via routing fn)
    workflow.add_conditional_edges(
        "decide_search_strategy",
        route_search,
        {"web_search": "web_search"},
    )

    # web_search → kb_search (always — kb_search self-skips if not configured)
    workflow.add_edge("web_search", "kb_search")

    # kb_search → synthesize (always)
    workflow.add_edge("kb_search", "synthesize")

    # synthesize → END
    workflow.add_edge("synthesize", END)

    # compile() validates the graph structure and returns a runnable object
    return workflow.compile()
