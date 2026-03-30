MyProjectCv/
├── .env
├── .gitignore
├── pytest.ini
├── requirements.txt
├── main.py                       # FastAPI entry → uvicorn main:app --reload
│
├── app/
│   ├── config.py                 # Pydantic Settings (.env loader)
│   ├── utils.py                  # JSON response parser + structlog logger
│   ├── models_pricing.py         # Gemini model pricing table
│   │
│   ├── models/
│   │   ├── state.py              # ComplianceState TypedDict (LangGraph state)
│   │   ├── requests.py           # ComplianceQueryRequest, IngestRuleRequest
│   │   └── responses.py          # ComplianceQueryResponse, HealthResponse, IngestResponse
│   │
│   ├── graph/
│   │   ├── builder.py            # StateGraph wiring + assemble_node (inline)
│   │   ├── edges.py              # route_after_rag(), should_loop_or_finish(), route_after_critique()
│   │   └── nodes/
│   │       ├── orchestrator.py   # Intent classifier (search/validate/explain)
│   │       ├── rag.py            # Hybrid search: Pinecone dense + MongoDB sparse
│   │       ├── validation.py     # LLM compliance check (temp=0.1)
│   │       ├── critique.py       # Hallucination reviewer (temp=0.0, 5 criteria)
│   │       └── remedier.py       # Remediation suggester (temp=0.3): triggered when is_compliant=False
│   │
│   ├── services/
│   │   ├── llm_service.py        # Gemini wrapper
│   │   ├── embedding_service.py  # gemini-embedding-001 (768 dims)
│   │   ├── pinecone_service.py   # Auto-creates index, query, upsert
│   │   └── mongodb_service.py    # Async Motor CRUD + indexes
│   │
│   ├── api/
│   │   ├── routes.py             # GET /health, POST /query, POST /seed
│   │   └── dependencies.py       # Graph + DB dependencies (lru_cache)
│   │
│   └── data/
│       ├── seed_rules.py         # Legacy DO-178B rules (unused)
│       └── ingest.py             # MISRA ingestion → MongoDB + Pinecone
│
├── data/
│   ├── misra_c_2023__headlines_for_cppcheck.txt
│   └── all_supported_model.txt
│
└── tests/
    ├── code_c_snippet_example.json
    ├── misra_test_sample.c
    └── unit/
        ├── graph/
        │   ├── test_builder.py
        │   ├── test_edges.py
        │   └── nodes/
        │       ├── test_orchestrator.py
        │       ├── test_rag.py
        │       ├── test_validation.py
        │       ├── test_critique.py
        │       └── test_remedier.py
        ├── services/
        │   └── test_mongodb_service.py
        └── utils/
            └── test_utils.py
