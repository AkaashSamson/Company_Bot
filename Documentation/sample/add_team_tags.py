import re
from pathlib import Path

ROADBLOCK_DATA = {
    "RB01": {
        "tags": "Infrastructure, VectorDB",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`NE`** (Neha - Ingestion & Vector Storage)",
        "tasks": "`[AB-4]`, `[NE-6.3]`, `[AB-5.1]`",
        "focus": "Embedding Model Registry & Vector Migrations"
    },
    "RB02": {
        "tags": "Caching, SemanticNLP",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-3.1]`, `[AB-4]`, `[AK-5.2]`",
        "focus": "Negation & Polarity Semantic Layer"
    },
    "RB03": {
        "tags": "Database, MultiTierSync",
        "lead": "**`RO`** (Roshan - Auth & Database)",
        "reviewer": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "tasks": "`[RO-5.1]`, `[AB-4]`, `[NE-1.1]`",
        "focus": "Multi-Tier Cache State Coordination"
    },
    "RB04": {
        "tags": "Infrastructure, ColdStart",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-4]`, `[AK-1.1]`, `[AB-6.1]`",
        "focus": "Lazy Loading & Thread Locks"
    },
    "RB05": {
        "tags": "DataQuality, UnicodeNorm",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`NE`** (Neha - Ingestion & Document)",
        "tasks": "`[AB-3.1]`, `[NE-6.1]`, `[AB-4]`",
        "focus": "Unicode NFKC Normalization Pipeline"
    },
    "RB06": {
        "tags": "Ingestion, TableParsing",
        "lead": "**`NE`** (Neha - Ingestion & Document)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[NE-6.1]`, `[NE-6.2]`, `[AK-5.1]`",
        "focus": "Table Preservation & Layout Parsers"
    },
    "RB07": {
        "tags": "Security, PromptInjection",
        "lead": "**`RO`** (Roshan - Auth & Security)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[RO-3.1]`, `[AK-5.2]`, `[NE-3.1]`",
        "focus": "RAG Ingestion Sanitization & Prompt Guardrails"
    },
    "RB08": {
        "tags": "RAG, RetrievalQuality",
        "lead": "**`NE`** (Neha - Ingestion & Document)",
        "reviewer": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "tasks": "`[NE-5.2]`, `[AB-5.2]`, `[AK-5.1]`",
        "focus": "Context Budget & Reranker Funnel"
    },
    "RB09": {
        "tags": "VectorDB, LifecycleSync",
        "lead": "**`NE`** (Neha - Ingestion & Document)",
        "reviewer": "**`RO`** (Roshan - Auth & Database)",
        "tasks": "`[NE-6.3]`, `[RO-4.1]`, `[NE-2.1]`",
        "focus": "Vector Lifecycle & In-Place Re-Upload"
    },
    "RB10": {
        "tags": "QueryNLP, Terminology",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`NE`** (Neha - Ingestion & Document)",
        "tasks": "`[AB-3.1]`, `[AB-3.3]`, `[NE-4.1]`",
        "focus": "Terminology Dictionary & Transliteration"
    },
    "RB11": {
        "tags": "Security, RBACBoundary",
        "lead": "**`RO`** (Roshan - Auth & Security)",
        "reviewer": "**`NE`** (Neha - Ingestion & Document)",
        "tasks": "`[RO-3.1]`, `[NE-6.3]`, `[AK-5.1]`",
        "focus": "Multi-Tenant RBAC & Vector Scoping"
    },
    "RB12": {
        "tags": "Security, CacheIsolation",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`RO`** (Roshan - Auth & Security)",
        "tasks": "`[AB-4]`, `[RO-3.1]`, `[AK-1.3]`",
        "focus": "Scoped Cache Keys & Auth Isolation"
    },
    "RB13": {
        "tags": "Auth, GraphHierarchy",
        "lead": "**`RO`** (Roshan - Auth & Security)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[RO-5.1]`, `[RO-5.2]`, `[RO-1.1]`",
        "focus": "Hierarchy Resolution & Graph Traversal"
    },
    "RB14": {
        "tags": "Auth, SessionLifecycle",
        "lead": "**`RO`** (Roshan - Auth & Security)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[RO-2.1]`, `[AK-1.1]`, `[AK-2.2]`",
        "focus": "Session Store & JWT Lifecycle"
    },
    "RB15": {
        "tags": "Security, DataBleed",
        "lead": "**`RO`** (Roshan - Auth & Security)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[RO-3.1]`, `[AK-5.2]`, `[RO-1.1]`",
        "focus": "Probe Boundaries & Information Bleed"
    },
    "RB16": {
        "tags": "LLM, FailoverCircuit",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-1.1]`, `[AB-1.2]`, `[AK-4]`",
        "focus": "Circuit Breaker & Failover Cascade"
    },
    "RB17": {
        "tags": "LLM, SchemaContracts",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-2]`, `[AK-5.2]`, `[NE-3.1]`",
        "focus": "Standard LLM Contracts & Citations"
    },
    "RB18": {
        "tags": "Core, TokenTruncation",
        "lead": "**`AK`** (Akaash Samson - Core Orchestration)",
        "reviewer": "**`RO`** (Roshan - UI & Auth)",
        "tasks": "`[AK-4]`, `[AK-5.2]`, `[RO-2.1]`",
        "focus": "Orchestrator Finish & UI Feedback"
    },
    "RB19": {
        "tags": "LLM, ContextLimits",
        "lead": "**`AK`** (Akaash Samson - Core Orchestration)",
        "reviewer": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "tasks": "`[AK-4]`, `[AB-1.1]`, `[NE-4.2]`",
        "focus": "Asymmetric Limits & Context Pruning"
    },
    "RB20": {
        "tags": "Observability, AsyncLogging",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`NE`** (Neha - Ingestion & Vector)",
        "tasks": "`[AB-1.1]`, `[NE-1.1]`, `[NE-1.3]`",
        "focus": "Async Logging & Bounded Thread Pools"
    },
    "RB21": {
        "tags": "Database, SQLiteConcurrency",
        "lead": "**`RO`** (Roshan - Auth & Database)",
        "reviewer": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "tasks": "`[RO-5.1]`, `[RO-2.1]`, `[NE-1.1]`",
        "focus": "SQLite Concurrency & WAL Optimization"
    },
    "RB22": {
        "tags": "Frontend, SessionState",
        "lead": "**`RO`** (Roshan - UI & Auth)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[RO-2.1]`, `[AK-1.1]`, `[AK-1.3]`",
        "focus": "Streamlit Session State & Multi-Tab Isolation"
    },
    "RB23": {
        "tags": "Infrastructure, MemoryLeaks",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-4]`, `[AK-1.1]`, `[NE-2.1]`",
        "focus": "Memory-Bounded Caches & Session TTL"
    },
    "RB24": {
        "tags": "Database, DualDBSync",
        "lead": "**`RO`** (Roshan - Auth & Database)",
        "reviewer": "**`NE`** (Neha - Ingestion & Document)",
        "tasks": "`[RO-5.1]`, `[NE-1.2]`, `[RO-4.1]`",
        "focus": "SQLite & MongoDB Soft-Delete Sync"
    },
    "RB25": {
        "tags": "Observability, SocketPools",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-6.1]`, `[AB-6.3]`, `[AK-3.2]`",
        "focus": "Pipeline Tracer & HTTP Connection Pools"
    },
    "RB26": {
        "tags": "Observability, EventLoopLag",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-6.1]`, `[AB-6.2]`, `[AK-3.4]`",
        "focus": "LangSmith Serialization & Event Loop Lag"
    },
    "RB27": {
        "tags": "DevOps, WindowsEnvironment",
        "lead": "**`AK`** (Akaash Samson - Core Orchestration)",
        "reviewer": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "tasks": "`[AK-1.2]`, `[AB-1.2]`, `[RO-7.1]`",
        "focus": "Windows PowerShell & Port Management"
    },
    "RB28": {
        "tags": "Security, PIIScrubbing",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`RO`** (Roshan - Auth & Security)",
        "tasks": "`[AB-6.1]`, `[RO-3.1]`, `[NE-1.1]`",
        "focus": "PII Regex Masking & Sensitive Logs"
    },
    "RB29": {
        "tags": "NLP, SemanticThresholds",
        "lead": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "reviewer": "**`AK`** (Akaash Samson - Core Orchestration)",
        "tasks": "`[AB-3.1]`, `[AB-4]`, `[AB-5.1]`",
        "focus": "Adaptive Thresholds & Semantic Jargon"
    },
    "RB30": {
        "tags": "Networking, GhostExecution",
        "lead": "**`AK`** (Akaash Samson - Core Orchestration)",
        "reviewer": "**`AB`** (Abhinav Bargi - Infrastructure & Caching)",
        "tasks": "`[AK-4]`, `[AB-1.1]`, `[AK-1.3]`",
        "focus": "Cancellation Tokens & Ghost LLM Invocations"
    },
}

def update_file():
    target_path = Path(r"c:\Users\ABHINAVNBARGI\OneDrive - McLaren Strategic Solutions US Inc\Documents\My Coding Space\Company-Bot\Company_Bot\Documentation\sample\30_Project_Roadblocks_Comprehensive.md")
    content = target_path.read_text(encoding="utf-8")

    # Update roadblocks
    sections = re.split(r"(?=### RB\d{2}:)", content)
    header = sections[0]
    rb_blocks = sections[1:]

    updated_blocks = []
    for block in rb_blocks:
        m = re.match(r"### (RB\d{2}):\s+(.+)", block)
        if not m:
            updated_blocks.append(block)
            continue
        rb_id = m.group(1)
        info = ROADBLOCK_DATA.get(rb_id)
        if not info:
            updated_blocks.append(block)
            continue

        # Format team tags block
        tag_lines = (
            f"- **Team Tags:** `[{info['tags']}]`\n"
            f"- **Team Ownership:** {info['lead']} | **Peer Review:** {info['reviewer']}\n"
            f"- **Roadmap Task Codes:** {info['tasks']}\n"
            f"- **Subsystem Focus:** `[{info['tags']}]` - {info['focus']}\n"
        )

        # Check if already tagged to avoid duplicate insertion
        if "- **Team Tags:**" in block:
            # Replace existing team tags block
            block = re.sub(
                r"- \*\*Team Tags:\*\*.*?- \*\*Subsystem Focus:\*\* [^\n]+\n",
                tag_lines,
                block,
                flags=re.DOTALL
            )
            updated_blocks.append(block)
            continue

        # Insert right after Blast Radius bullet
        if "- **Blast Radius:**" in block:
            parts = re.split(r"(- \*\*Blast Radius:\*\* [^\n]+\n)", block)
            if len(parts) >= 3:
                block_updated = parts[0] + parts[1] + tag_lines + "".join(parts[2:])
            else:
                block_updated = block
        else:
            block_updated = block

        updated_blocks.append(block_updated)

    final_content = header + "".join(updated_blocks)
    target_path.write_text(final_content, encoding="utf-8")
    print(f"Successfully updated {len(updated_blocks)} roadblocks with team tags!")

if __name__ == "__main__":
    update_file()
