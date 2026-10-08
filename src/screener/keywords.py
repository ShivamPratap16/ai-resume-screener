import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    name: str
    groups: tuple[str, ...]
    pattern: re.Pattern


KNOWN_GROUPS = frozenset({
    "python", "python_eco", "classic_ml", "ml_platform",
    "ai_agents", "ai_tools", "ai_framework", "llm_api", "ai_retrieval", "ai_state", "ai_eval", "ai_product", "ai_buzz",
    "backend", "database", "async", "cloud", "gcp", "docker", "deploy", "frontend", "js", "other_lang",
    "testing", "caching", "queue", "observability", "concurrency", "resilience", "architecture", "data", "impact",
})


def _t(name: str, groups: str, regex: str) -> Term:
    # A misspelt group would otherwise just never score, so fail loudly at import time.
    if unknown := set(groups.split()) - KNOWN_GROUPS:
        raise ValueError(f"Term {name!r} uses unknown group(s): {sorted(unknown)}")
    return Term(name, tuple(groups.split()), re.compile(regex, re.IGNORECASE))


TERMS: list[Term] = [
    _t("Python", "python", r"\bpython3?\b"),
    _t("FastAPI", "python_eco backend", r"\bfast\s?api\b"),
    _t("Django", "python_eco backend", r"\bdjango\b"),
    _t("Flask", "python_eco backend", r"\bflask\b"),
    _t("Pydantic", "python_eco", r"\bpydantic\b"),
    _t("pandas", "python_eco data", r"\bpandas\b"),
    _t("NumPy", "python_eco", r"\bnumpy\b"),
    _t("PyTorch", "python_eco classic_ml", r"\bpytorch\b"),
    _t("TensorFlow", "python_eco classic_ml", r"\btensorflow\b|\bkeras\b"),
    _t("scikit-learn", "python_eco classic_ml", r"\bscikit[- ]learn\b|\bsklearn\b"),
    _t("SQLAlchemy", "python_eco backend", r"\bsqlalchemy\b"),
    _t("Celery", "python_eco backend queue", r"\bcelery\b"),
    _t("Streamlit", "python_eco frontend", r"\bstreamlit\b"),
    _t("pytest", "python_eco testing", r"\bpytest\b"),
    _t("asyncio", "python_eco async concurrency", r"\basyncio\b"),
    _t("Async programming", "async concurrency", r"\basync\s*/\s*await\b|\basync(?:hronous)?\b"),

    _t("LangGraph", "ai_agents ai_framework", r"\blang\s?graph\b"),
    _t("Google ADK", "ai_agents ai_framework", r"\bgoogle\s+adk\b|\badk\b|\bagent development kit\b"),
    _t("CrewAI", "ai_agents ai_framework", r"\bcrew\s?ai\b"),
    _t("AutoGen", "ai_agents ai_framework", r"\bautogen\b"),
    _t("AI agents", "ai_agents", r"\bagentic\b|\b(?:ai|llm|autonomous|conversational|research|coding|support|react|sql|planning|planner)[- ]agents?\b|\bagents?\s+(?:that|which|with|using|to)\b"),
    _t("Multi-agent", "ai_agents", r"\bmulti[- ]?agents?\b"),
    _t("Tool calling", "ai_agents ai_tools", r"\b(?:tool|function)[- ]calling\b|\btool[- ]use\b"),
    _t("MCP", "ai_agents ai_tools", r"\bmodel context protocol\b|\bmcp\b"),
    _t("LangChain", "ai_framework", r"\blang\s?chain(?:\.js|js)?\b"),
    _t("LlamaIndex", "ai_framework ai_retrieval", r"\bllama\s?index\b"),
    # Hugging Face is used as often for CV/classical models, so on its own it doesn't prove LLM work.
    _t("Hugging Face", "ml_platform", r"\bhugging\s?face\b|\btransformers\b"),
    _t("OpenAI API", "ai_framework llm_api", r"\bopen\s?ai\b|\bgpt-?\d(?:\.\d)?o?\b|\bchat\s?gpt api\b"),
    _t("Claude API", "ai_framework llm_api", r"\banthropic\b|\bclaude\s+(?:api|sdk|sonnet|opus|haiku)\b"),
    _t("Gemini", "ai_framework llm_api", r"\bgemini\b"),
    _t("Ollama", "ai_framework", r"\bollama\b|\bvllm\b"),
    _t("Open LLMs", "ai_framework llm_api", r"\bllama\s?\d?(?:\.\d)?\b|\bmistral\b|\bgroq\b|\blitellm\b|\bnvidia nim\b|\bqwen\b|\bdeepseek\b|\bbedrock\b"),
    _t("LLM", "ai_framework", r"\bllms?\b|\blarge language models?\b|\bgen(?:erative)?\s?ai\b"),
    _t("LLM fine-tuning", "ai_framework", r"\bfine[- ]?tun(?:e|ed|ing)\s+(?:an?\s+)?(?:open[- ]source\s+)?(?:llms?|language models?|llama|mistral|gpt|bert)\b|\bq?lora\b"),
    _t("RAG", "ai_retrieval", r"\brag\b|\bretrieval[- ]augmented\b"),
    _t("Embeddings", "ai_retrieval", r"\bembeddings?\b"),
    _t("Vector search", "ai_retrieval", r"\bvector\s+(?:search|store|database|db|index)\b|\bsemantic search\b|\bhybrid search\b"),
    _t("FAISS", "ai_retrieval", r"\bfaiss\b"),
    _t("ChromaDB", "ai_retrieval", r"\bchroma(?:db)?\b"),
    _t("Pinecone", "ai_retrieval", r"\bpinecone\b"),
    _t("Qdrant", "ai_retrieval", r"\bqdrant\b"),
    _t("Weaviate", "ai_retrieval", r"\bweaviate\b"),
    _t("pgvector", "ai_retrieval", r"\bpgvector\b"),
    _t("Reranking", "ai_retrieval", r"\bre-?rank(?:ing|er)?\b"),
    _t("Chunking", "ai_retrieval data", r"\bchunking\b|\bchunks?\b"),
    # Plain "state"/"memory" is usually UI state or hardware; require phrasing that implies AI/agent state.
    _t("Agent state / memory", "ai_state",
       r"\bstateful\b|\bstate\s?graph\b|\bcheckpoint(?:s|ing|ers?)?\b|\bmemory\s?(?:saver|store|layer|module)\b"
       r"|\b(?:conversation(?:al)?|chat|session|agent|graph|shared|persistent|long[- ]term|short[- ]term)\s+(?:memory|state|history|context)\b"
       r"|\bstate\b(?=[^.]{0,80}\bagents?\b)"),
    _t("LLM evaluation", "ai_eval", r"\beval(?:uation|s)?\b|\bragas\b|\bdeepeval\b|\bllm[- ]as[- ](?:a[- ])?judge\b|\bgolden (?:set|dataset)\b|\bllm[- ]to[- ]llm\b|\bscoring engine\b|\bhallucination\b"),
    _t("Structured output", "ai_product", r"\bstructured outputs?\b|\bjson schema\b|\bguardrails?\b"),
    _t("Prompt engineering", "ai_buzz", r"\bprompt engineering\b|\bprompts?\b"),
    _t("Machine learning", "ai_buzz", r"\bmachine learning\b|\bdeep learning\b|\bartificial intelligence\b|\bai\b"),

    _t("PostgreSQL", "backend database", r"\bpostgre(?:s|sql)\b"),
    _t("Redis", "backend database caching", r"\bredis\b"),
    _t("MySQL", "backend database", r"\bmysql\b"),
    _t("MongoDB", "backend database", r"\bmongo(?:db)?\b"),
    _t("SQL", "backend database", r"\bsql\b|\bsqlite\b"),
    _t("NoSQL stores", "backend database", r"\bfirestore\b|\bdynamodb\b|\bsupabase\b|\bfirebase\b"),
    _t("REST API", "backend", r"\brest(?:ful)?\s+apis?\b|\bapi endpoints?\b|\bendpoints?\b|\bgraphql\b|\bgrpc\b|\bwebsockets?\b"),

    _t("GCP", "cloud gcp", r"\bgcp\b|\bgoogle cloud\b|\bcloud run\b|\bbigquery\b|\bvertex ai\b|\bgke\b|\bcloud functions\b"),
    _t("AWS", "cloud", r"\baws\b|\bamazon web services\b|\blambda\b|\bec2\b|\bs3\b"),
    _t("Azure", "cloud", r"\bazure\b"),
    _t("Docker", "cloud docker", r"\bdocker(?:ized|file)?\b|\bdocker[- ]compose\b|\bcontaineri[sz]ed\b"),
    _t("Kubernetes", "cloud deploy", r"\bkubernetes\b|\bk8s\b"),
    _t("CI/CD", "cloud deploy", r"\bci\s?/\s?cd\b|\bgithub actions\b"),
    _t("Deployment", "cloud deploy", r"\bdeployed\b|\bdeployment\b|\bin production\b|\bproduction\b"),

    _t("React", "frontend", r"\breact(?:\.js|js)?\b(?![- ]agent)(?!\s+native)"),
    _t("Next.js", "frontend", r"\bnext\.?js\b"),
    _t("TypeScript", "frontend js", r"\btypescript\b"),
    _t("JavaScript", "frontend js", r"\bjavascript\b|\bnode\.?js\b|\bexpress(?:\.js)?\b"),
    _t("Java", "other_lang", r"\bjava\b"),
    _t("Spring Boot", "other_lang backend", r"\bspring(?:\s?boot)?\b"),
    _t("C++", "other_lang", r"\bc\+\+"),

    _t("Testing", "testing", r"\bunit tests?\b|\bintegration tests?\b|\btest coverage\b|\btests?\b|\btesting\b"),
    _t("Caching", "caching", r"\bcach(?:e|ed|ing)\b"),
    _t("Queues", "queue", r"\bkafka\b|\brabbitmq\b|\bmessage queues?\b|\bqueues?\b|\bpub/sub\b|\bsqs\b"),
    _t("Observability", "observability", r"\bobservability\b|\bmonitoring\b|\blogging\b|\bprometheus\b|\bgrafana\b|\bopentelemetry\b|\btracing\b|\blangsmith\b|\blangfuse\b"),
    _t("Concurrency", "concurrency", r"\bconcurren(?:cy|t)\b|\bmulti-?threading\b|\bparallel\b|\bsemaphore\b"),
    _t("Failure handling", "resilience", r"\bretr(?:y|ies)\b|\bfallbacks?\b|\bcircuit breaker\b|\brate[- ]limit(?:ing|s)?\b|\bidempoten(?:t|cy)\b|\btimeouts?\b"),
    _t("Architecture", "architecture", r"\bmicroservices?\b|\barchitecture\b|\bevent[- ]driven\b|\bdesign patterns?\b"),
    _t("Measured impact", "impact", r"\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?[kKmM]?\+?\s+(?:users|requests|documents|tickets|queries|customers|calls|records)\b|\bp9[59]\b|\blatency\b|\bin production\b"),
    _t("Data pipeline", "data",r"\bpipelines?\b|\bingestion\b|\betl\b|\bpre-?processing\b|\bparsing\b|\bscrap(?:er|ing)\b"),
]

# Groups that prove real LLM/agentic exposure (generic "AI" buzzwords don't count).
AI_QUALIFYING_GROUPS = {"ai_agents", "ai_retrieval", "ai_framework"}
# Signals that make an AI project more than a single LLM call.
AI_DEPTH_GROUPS = {"ai_agents", "ai_retrieval", "ai_state", "ai_eval", "ai_product", "data", "database", "backend"}
ENGINEERING_GROUPS = ("testing", "caching", "queue", "observability", "concurrency", "resilience", "architecture")

ACTION_VERBS = re.compile(
    r"\b(built|build|building|developed|designed|implemented|created|engineered|architected|led|"
    r"deployed|integrated|optimi[sz]ed|wrote|automated|reduced|improved|added|shipped|migrated|"
    r"orchestrat\w*|trained|evaluated|used|using|leveraged|contributed|maintained)\b",
    re.IGNORECASE,
)
TUTORIAL_CUES = re.compile(
    r"\b(tutorial|followed (?:a|the)|youtube|udemy|coursera|course project|guided project|clone of|"
    r"codealong|code-along|bootcamp assignment|guided (?:hands-on )?labs?|virtual internship)\b",
    re.IGNORECASE,
)
WRAPPER_CUES = re.compile(
    r"\b(wrapper|chatbot|calls? (?:the )?(?:openai|gpt|gemini|claude|llm) api|"
    r"sends? (?:the )?(?:user )?(?:prompt|query|input) to)\b",
    re.IGNORECASE,
)
# Using an AI coding assistant is not building an AI system.
AI_CODING_TOOL_CUES = re.compile(
    r"\b(cursor|copilot|claude code|codex|windsurf|ai[- ]assisted|chatgpt|ai (?:coding |development )?tools)\b",
    re.IGNORECASE,
)
NOT_GENUINE_CUES = re.compile(
    r"\b(currently learning|now learning|learning to|beginner in|basic knowledge of|interested in|"
    r"plan(?:ning)? to learn|want to learn|aspiring)\b",
    re.IGNORECASE,
)
