"""Local document embedding and retrieval using Ollama and ChromaDB."""

import chromadb
import json
import logging
import time
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_PATH = PROJECT_ROOT / "data" / "vector_store"
COLLECTION_NAME = "reverse_logistics_knowledge"
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"

logger = logging.getLogger(__name__)


def embed_text(text):
    """Generate a local embedding using Ollama."""
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text,
    }).encode("utf-8")

    request = Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    with urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    elapsed = time.perf_counter() - started

    embeddings = result.get("embeddings", [])
    if not embeddings or not embeddings[0]:
        raise RuntimeError("Ollama returned an empty embedding.")

    logger.info(
        "Embedding timing: model=%s elapsed=%.3fs input_chars=%d",
        EMBEDDING_MODEL,
        elapsed,
        len(text),
    )
    return embeddings[0]


def get_collection():
    """Return the persistent local ChromaDB collection."""
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def add_documents(documents):
    """Index documents shaped as [{'id': ..., 'text': ..., 'source': ...}]."""
    if not documents:
        return 0

    collection = get_collection()
    ids = []
    texts = []
    metadatas = []
    embeddings = []

    for document in documents:
        doc_id = str(document["id"]).strip()
        content = str(document["text"]).strip()
        source = str(document.get("source", "unknown"))

        if not doc_id or not content:
            raise ValueError("Every document needs a non-empty id and text.")

        ids.append(doc_id)
        texts.append(content)
        metadatas.append({"source": source})
        embeddings.append(embed_text(content))

    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    return len(ids)


def search_documents(query, n_results=3):
    """Retrieve the most relevant local document passages."""
    if not query or not query.strip():
        raise ValueError("Search query must not be empty.")
    if n_results < 1:
        raise ValueError("n_results must be at least 1.")

    total_started = time.perf_counter()
    collection_started = time.perf_counter()
    collection = get_collection()
    collection_seconds = time.perf_counter() - collection_started

    count_started = time.perf_counter()
    collection_count = collection.count()
    count_seconds = time.perf_counter() - count_started

    if collection_count == 0:
        logger.info(
            "RAG timing: collection=%.3fs count=%.3fs embedding=0.000s "
            "vector_query=0.000s total=%.3fs collection_count=0",
            collection_seconds,
            count_seconds,
            time.perf_counter() - total_started,
        )
        return []

    embedding_started = time.perf_counter()
    query_embedding = embed_text(query)
    embedding_seconds = time.perf_counter() - embedding_started

    query_started = time.perf_counter()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection_count),
        include=["documents", "metadatas", "distances"],
    )
    vector_query_seconds = time.perf_counter() - query_started

    matches = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for index, content in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        matches.append({
            "text": content,
            "source": metadata.get("source", "unknown"),
            "distance": distance,
        })

    logger.info(
        "RAG timing: collection=%.3fs count=%.3fs embedding=%.3fs "
        "vector_query=%.3fs total=%.3fs collection_count=%d results=%d",
        collection_seconds,
        count_seconds,
        embedding_seconds,
        vector_query_seconds,
        time.perf_counter() - total_started,
        collection_count,
        len(matches),
    )
    return matches
