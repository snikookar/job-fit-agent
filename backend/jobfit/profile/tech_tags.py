"""A small technology vocabulary used to tag chunks (`tech_tags` metadata) and to help
the offline heuristic provider recognize skills in job postings."""

from __future__ import annotations

import re
from functools import lru_cache

# canonical name -> aliases (matched case-insensitively on word boundaries)
TECH_VOCAB: dict[str, list[str]] = {
    # Languages
    "Python": ["python"],
    "Java": ["java"],
    "Kotlin": ["kotlin"],
    "Scala": ["scala"],
    "Go": ["golang", "go"],
    "Rust": ["rust"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"],
    "SQL": ["sql"],
    "R": ["r"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "Swift": ["swift"],
    "Bash": ["bash", "shell scripting"],
    # Backend / web
    "FastAPI": ["fastapi"],
    "Django": ["django", "django rest framework", "drf"],
    "Flask": ["flask"],
    "Spring": ["spring boot", "spring"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Express": ["express.js", "express"],
    "NestJS": ["nestjs"],
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "Vue": ["vue", "vue.js"],
    "Angular": ["angular"],
    "Tailwind": ["tailwind", "tailwindcss"],
    "GraphQL": ["graphql"],
    "REST": ["rest", "restful", "rest api", "rest apis"],
    "gRPC": ["grpc"],
    "Microservices": ["microservices", "microservice"],
    # Data stores
    "PostgreSQL": ["postgresql", "postgres"],
    "pgvector": ["pgvector"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "opensearch"],
    "Snowflake": ["snowflake"],
    "BigQuery": ["bigquery"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],
    "Qdrant": ["qdrant"],
    "Pinecone": ["pinecone"],
    "Weaviate": ["weaviate"],
    "Vector databases": [
        "vector database",
        "vector databases",
        "vector db",
        "vector store",
        "pgvector",
        "qdrant",
        "pinecone",
        "weaviate",
        "chroma",
        "milvus",
    ],
    # Messaging / data engineering
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq"],
    "Celery": ["celery"],
    "Airflow": ["airflow", "apache airflow"],
    "Spark": ["spark", "pyspark"],
    "dbt": ["dbt"],
    "ETL": ["etl", "elt", "data pipelines", "data pipeline"],
    "pandas": ["pandas"],
    "NumPy": ["numpy"],
    # ML / AI
    "Machine learning": ["machine learning", "ml"],
    "Deep learning": ["deep learning"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow", "keras"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "Hugging Face": ["hugging face", "huggingface", "transformers"],
    "LLM": [
        "llm",
        "llms",
        "large language model",
        "large language models",
        "genai",
        "generative ai",
    ],
    "RAG": ["rag", "retrieval-augmented generation", "retrieval augmented generation"],
    "LangChain": ["langchain"],
    "LangGraph": ["langgraph"],
    "LlamaIndex": ["llamaindex", "llama index"],
    "OpenAI": ["openai", "gpt-4", "gpt-4o", "chatgpt"],
    "Prompt engineering": ["prompt engineering"],
    "Fine-tuning": ["fine-tuning", "fine tuning", "fine-tuned", "finetuning"],
    "Embeddings": ["embeddings", "embedding"],
    "NLP": ["nlp", "natural language processing"],
    "Computer vision": ["computer vision"],
    "LLM evaluation": ["llm evaluation", "evals", "evaluation harness"],
    "Agents": ["ai agents", "agentic", "multi-agent", "agents"],
    "MLOps": ["mlops"],
    "MLflow": ["mlflow"],
    # Infrastructure / cloud
    "Docker": ["docker", "containers", "containerized"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Helm": ["helm"],
    "Terraform": ["terraform"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "Linux": ["linux"],
    "CI/CD": ["ci/cd", "ci", "continuous integration", "continuous delivery"],
    "GitHub Actions": ["github actions"],
    "GitLab CI": ["gitlab ci"],
    "Git": ["git"],
    "Observability": ["observability", "monitoring", "opentelemetry", "prometheus", "grafana"],
    "OpenTelemetry": ["opentelemetry"],
    "Prometheus": ["prometheus"],
    # Practices
    "Testing": ["pytest", "unit tests", "integration tests", "testing", "tdd"],
    "Agile": ["agile", "scrum", "kanban"],
    "System design": ["system design", "distributed systems"],
    "Security": ["security", "oauth", "authentication"],
}


@lru_cache
def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    out = []
    for canonical, aliases in TECH_VOCAB.items():
        alts = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
        # Word-ish boundaries that also work for tokens like "c++" and "node.js".
        out.append((canonical, re.compile(rf"(?<![\w+#.])(?:{alts})(?![\w+#])", re.IGNORECASE)))
    return out


# Aliases that are too ambiguous to trust in free text unless written in a tech-ish way.
_CASE_SENSITIVE = {
    "Go": re.compile(r"\bGo\b"),
    "R": re.compile(r"\bR\b"),
    "REST": re.compile(r"\bREST"),
}


def extract_tech_tags(text: str) -> list[str]:
    found: list[str] = []
    for canonical, pattern in _patterns():
        if canonical in _CASE_SENSITIVE:
            if (
                canonical == "Go"
                and re.search(r"\bgolang\b", text, re.IGNORECASE)
                or _CASE_SENSITIVE[canonical].search(text)
            ):
                found.append(canonical)
            continue
        if pattern.search(text):
            found.append(canonical)
    return found
