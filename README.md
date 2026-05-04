# 🔬 Agentic Research Assistant

An AI-powered research agent that automatically gathers, analyzes, and synthesizes information from web sources and knowledge bases to generate comprehensive research reports.

## Features

- **Automated Research**: Validates topics, decomposes them into sub-questions, and executes targeted searches
- **Dual Search Strategy**: Combines web search (via Tavily) with optional knowledge base search (via Qdrant)
- **Streaming UI**: Real-time progress updates as the agent thinks and researches
- **Structured Reports**: Generates professional markdown reports with citations and sources
- **PDF Export**: Download research reports as formatted PDFs
- **History Management**: Track and revisit past research reports
- **LLM-Powered**: Uses Google's Gemini 2.5 Flash for intelligent analysis and synthesis

## Architecture

The project consists of three main components:

### Backend (`FastAPI`)
- **main.py**: FastAPI server setup with lifespan management
- **agent.py**: LangGraph-based research agent with nodes for validation, search, and synthesis
- **api.py**: REST API endpoints for research, history, and PDF generation
- **database.py**: SQLite persistence layer for storing reports
- **config.py**: Environment configuration management

### Frontend (`Streamlit`)
- **frontend.py**: Interactive UI for submitting research topics and viewing results
- Real-time streaming of agent thinking steps
- History sidebar for accessing previous reports

### Supporting Modules
- **model.py**: Pydantic models for request/response validation
- **pdf_generator.py**: PDF generation from markdown reports

## Tech Stack

- **Backend**: FastAPI, LangGraph, LangChain
- **LLM**: Google Generative AI (Gemini 2.5 Flash)
- **Search**: Tavily API (web search), Qdrant (vector search)
- **Frontend**: Streamlit
- **Database**: SQLite
- **PDF Generation**: ReportLab

## Installation

### Prerequisites
- Python 3.11+
- API Keys:
  - Google Generative AI (Gemini)
  - Tavily Search API
  - (Optional) Qdrant vector database access

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/madan-genai/Agentic-Research-Assistant.git
   cd Agentic-Research-Assistant
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables** (create `.env` file):
   ```env
   GEMINI_API_KEY=your_gemini_api_key
   TAVILY_API_KEY=your_tavily_api_key
   QDRANT_URL=https://your-qdrant-instance.cloud.qdrant.io  # Optional
   QDRANT_API_KEY=your_qdrant_api_key  # Optional
   QDRANT_COLLECTION=research-agent  # Optional
   ```

## Usage

### Start the Backend Server

```bash
python -m uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

API endpoints:
- `POST /research` - Start a new research task (SSE stream)
- `GET /history` - List all past research reports
- `GET /history/{report_id}` - Retrieve a specific report
- `GET /history/{report_id}/pdf` - Download report as PDF
- `DELETE /history/{report_id}` - Delete a report
- `GET /health` - Health check

### Start the Frontend

```bash
streamlit run frontend.py
```

The frontend will be available at `http://localhost:8501`

## How It Works

### Research Flow

1. **Topic Validation**: LLM evaluates if the topic is suitable for research
2. **Query Analysis**: Topic is decomposed into 3 focused sub-questions and search strategy is chosen
3. **Search Strategy Decision**: Routes to either web-only or hybrid search (web + knowledge base)
4. **Web Search**: Tavily searches for up to 25 relevant URLs across all sub-questions
5. **Knowledge Base Search** (optional): Qdrant vector search for relevant chunks
6. **Synthesis**: LLM combines all findings into a structured report
7. **Storage**: Report is saved to SQLite with sources and metadata

### Streaming Output

All research progress is streamed to the frontend as Server-Sent Events (SSE):
- `start`: Research begins
- `node_start`: Each agent node execution begins
- `thinking`: Agent thinking steps and reasoning
- `complete`: Research finished with final report
- `summary`: Summary statistics
- `error`: Any errors encountered

## Project Structure

```
Agentic-Research-Assistant/
├── main.py                 # FastAPI application entry point
├── agent.py               # LangGraph research agent logic
├── api.py                 # REST API endpoints
├── database.py            # SQLite operations
├── config.py              # Configuration management
├── model.py               # Pydantic models
├── pdf_generator.py       # PDF generation
├── frontend.py            # Streamlit UI
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Key Components Explained

### ResearchState (TypedDict)
Tracks the full state of a research task throughout the agent's execution:
- `topic`: The research topic
- `sub_questions`: 3 focused research questions
- `search_strategy`: "web_only" or "both"
- `web_results`: URLs and content from web search
- `vector_results`: Chunks from knowledge base
- `report`: Generated markdown report
- `thinking_steps`: Agent's reasoning logs

### Graph Structure
The agent uses LangGraph with conditional routing:
- **validate_topic** → **analyze_query** → **decide_search_strategy**
- Routes to either **web_search** (alone) or **web_search + kb_search** (together)
- Both routes converge at **synthesize** → **END**

## Configuration Options

### Model Selection
- Default: `gemini-2.5-flash`
- Adjust in `config.py` or via `llm_model` environment variable

### Search Limits
- Maximum URLs per research: 25 (configurable in `agent.py`)
- Results per sub-question: 7 URLs

### Database
- Default path: `research_history.db`
- Configurable via `db_path` in `.env`

## Error Handling

The agent handles errors gracefully:
- Invalid topics are rejected at validation stage
- Failed API calls are logged with user-friendly messages
- Database errors are caught and reported
- SSE stream includes error events for frontend display

## Future Enhancements

- [ ] Support for multiple LLM providers
- [ ] Advanced caching for search results
- [ ] Custom report templates
- [ ] Batch research processing
- [ ] API rate limiting and authentication
- [ ] Docker containerization
- [ ] Deployment guides (AWS, GCP, etc.)

## License

MIT

## Contact

For questions or issues, please open an issue on GitHub or contact the maintainers.

---

**Built with ❤️ using LangGraph, FastAPI, and Streamlit**
