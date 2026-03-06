"""
Re-ingest individual documents into the Pinecone index.

Use this when check_currency.py flags a changed source,
or when you need to update a specific document.

Usage:
    python -m app.reingest --file path/to/document.pdf --namespace guides
    python -m app.reingest --file path/to/document.pdf --namespace acts --replace
    python -m app.reingest --list-namespaces
    python -m app.reingest --list-docs acts

The --replace flag deletes existing vectors for that document before ingesting.
Without it, new vectors are added alongside existing ones (use for new docs).
"""
import os
import sys
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from pinecone import Pinecone
from openai import OpenAI

# Import the ingest pipeline components
# Adjust these imports based on your actual ingest.py structure
try:
    from .ingest import chunk_document, extract_metadata
except ImportError:
    print("Warning: Could not import from ingest.py — using standalone chunking")
    chunk_document = None
    extract_metadata = None

EMBED_MODEL = "text-embedding-3-small"

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot"))


def get_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(input=[text], model=EMBED_MODEL)
    return response.data[0].embedding


def list_namespaces():
    """Show all namespaces and their vector counts."""
    stats = index.describe_index_stats()
    namespaces = stats.get("namespaces", {})
    
    print(f"\n{'='*50}")
    print(f"Index: {os.getenv('PINECONE_INDEX_NAME')}")
    print(f"Total vectors: {stats.get('total_vector_count', 0)}")
    print(f"{'='*50}")
    
    for ns, info in sorted(namespaces.items()):
        print(f"  {ns:<25} {info.get('vector_count', 0):>6} vectors")


def list_docs_in_namespace(namespace: str):
    """List unique document titles in a namespace."""
    # Pinecone doesn't support listing by metadata directly,
    # so we do a dummy query to sample vectors
    stats = index.describe_index_stats()
    ns_info = stats.get("namespaces", {}).get(namespace)
    
    if not ns_info:
        print(f"Namespace '{namespace}' not found.")
        return
    
    print(f"\nNamespace: {namespace} ({ns_info.get('vector_count', 0)} vectors)")
    print(f"{'─'*50}")
    print("Note: This samples up to 100 vectors to find unique documents.")
    print("Some documents may not appear if the namespace is very large.\n")
    
    # Use a zero vector to get a random sample
    dim = 1536  # text-embedding-3-small dimension
    dummy = [0.0] * dim
    
    results = index.query(
        vector=dummy,
        top_k=100,
        namespace=namespace,
        include_metadata=True
    )
    
    titles = set()
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        title = meta.get("display_name") or meta.get("title") or "Unknown"
        doc_type = meta.get("doc_type", "?")
        titles.add((title, doc_type))
    
    for title, dtype in sorted(titles):
        print(f"  [{dtype}] {title}")


def delete_document_vectors(namespace: str, doc_title: str) -> int:
    """
    Delete all vectors for a specific document in a namespace.
    
    Uses metadata filtering to find and delete vectors.
    Returns count of deleted vectors.
    """
    # Pinecone's delete with metadata filter
    # Note: This requires the metadata field to be indexed
    # We'll use a query + delete approach as a fallback
    
    dim = 1536
    dummy = [0.0] * dim
    
    # Find vectors matching this document
    results = index.query(
        vector=dummy,
        top_k=1000,  # Get as many as possible
        namespace=namespace,
        include_metadata=True,
        filter={"display_name": {"$eq": doc_title}}
    )
    
    matches = results.get("matches", [])
    if not matches:
        # Try with 'title' field instead
        results = index.query(
            vector=dummy,
            top_k=1000,
            namespace=namespace,
            include_metadata=True,
            filter={"title": {"$eq": doc_title}}
        )
        matches = results.get("matches", [])
    
    if not matches:
        print(f"  No existing vectors found for '{doc_title}' in {namespace}")
        return 0
    
    ids_to_delete = [m["id"] for m in matches]
    
    # Delete in batches of 100
    deleted = 0
    for i in range(0, len(ids_to_delete), 100):
        batch = ids_to_delete[i:i+100]
        index.delete(ids=batch, namespace=namespace)
        deleted += len(batch)
    
    print(f"  Deleted {deleted} existing vectors for '{doc_title}'")
    return deleted


def reingest_document(
    file_path: str,
    namespace: str,
    replace: bool = False,
    doc_type: str = None,
    display_name: str = None,
):
    """
    Re-ingest a single document into the index.
    
    Args:
        file_path: Path to the document file
        namespace: Target namespace
        replace: If True, delete existing vectors for this doc first
        doc_type: Override doc_type metadata
        display_name: Override display_name metadata
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    # Determine display name
    if not display_name:
        display_name = path.stem.replace("-", " ").replace("_", " ").title()
    
    # Determine doc type from namespace if not specified
    if not doc_type:
        type_map = {
            "acts": "legislation",
            "codes": "code_of_practice",
            "guides": "guide",
            "procedures": "procedure",
            "sectors": "sector_order",
            "statutory-instruments": "statutory_instrument",
            "unions": "union_info",
            "eu": "eu_directive",
        }
        doc_type = type_map.get(namespace, "document")
    
    print(f"\n{'='*50}")
    print(f"Re-ingesting: {display_name}")
    print(f"File: {path}")
    print(f"Namespace: {namespace}")
    print(f"Doc type: {doc_type}")
    print(f"Replace: {replace}")
    print(f"{'='*50}")
    
    # Step 1: Delete existing if replacing
    if replace:
        delete_document_vectors(namespace, display_name)
    
    # Step 2: Read and chunk the document
    if chunk_document:
        # Use the ingest pipeline's chunking
        chunks = chunk_document(str(path))
    else:
        # Basic fallback chunking
        print("  Using basic chunking (ingest.py not available)")
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Simple chunking by ~500 words
        words = text.split()
        chunk_size = 400
        overlap = 50
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk_text = " ".join(words[i:i + chunk_size])
            chunks.append({
                "text": chunk_text,
                "section_id": f"chunk_{i // (chunk_size - overlap) + 1}",
            })
    
    if not chunks:
        print("  Error: No chunks produced from document")
        return
    
    print(f"  Produced {len(chunks)} chunks")
    
    # Step 3: Embed and upsert
    vectors = []
    for i, chunk in enumerate(chunks):
        chunk_text = chunk if isinstance(chunk, str) else chunk.get("text", "")
        section_id = chunk.get("section_id", f"chunk_{i+1}") if isinstance(chunk, dict) else f"chunk_{i+1}"
        
        if not chunk_text.strip():
            continue
        
        embedding = get_embedding(chunk_text)
        
        # Generate a deterministic ID
        doc_hash = hashlib.md5(f"{display_name}:{section_id}".encode()).hexdigest()[:12]
        vector_id = f"{namespace}-{doc_hash}-{i}"
        
        vectors.append({
            "id": vector_id,
            "values": embedding,
            "metadata": {
                "text": chunk_text[:2000],  # Pinecone metadata limit
                "display_name": display_name,
                "doc_type": doc_type,
                "section_id": section_id,
                "source_file": path.name,
                "ingested_at": datetime.now().isoformat(),
                "namespace": namespace,
            }
        })
        
        if (i + 1) % 10 == 0:
            print(f"  Embedded {i+1}/{len(chunks)} chunks...")
    
    # Upsert in batches of 50
    total_upserted = 0
    for i in range(0, len(vectors), 50):
        batch = vectors[i:i+50]
        index.upsert(vectors=batch, namespace=namespace)
        total_upserted += len(batch)
    
    print(f"\n  ✅ Upserted {total_upserted} vectors to '{namespace}'")
    print(f"  Document: {display_name}")
    
    # Verify
    stats = index.describe_index_stats()
    ns_count = stats.get("namespaces", {}).get(namespace, {}).get("vector_count", 0)
    print(f"  Namespace '{namespace}' now has {ns_count} vectors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-ingest documents into Pinecone")
    parser.add_argument("--file", type=str, help="Path to document file")
    parser.add_argument("--namespace", type=str, help="Target namespace")
    parser.add_argument("--replace", action="store_true", help="Delete existing vectors for this doc first")
    parser.add_argument("--doc-type", type=str, help="Override doc_type metadata")
    parser.add_argument("--display-name", type=str, help="Override display_name metadata")
    parser.add_argument("--list-namespaces", action="store_true", help="List all namespaces")
    parser.add_argument("--list-docs", type=str, metavar="NAMESPACE", help="List documents in a namespace")
    
    args = parser.parse_args()
    
    if args.list_namespaces:
        list_namespaces()
    elif args.list_docs:
        list_docs_in_namespace(args.list_docs)
    elif args.file and args.namespace:
        reingest_document(
            file_path=args.file,
            namespace=args.namespace,
            replace=args.replace,
            doc_type=args.doc_type,
            display_name=args.display_name,
        )
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python -m app.reingest --list-namespaces")
        print("  python -m app.reingest --list-docs guides")
        print("  python -m app.reingest --file docs/guides/ci-minimum-wage.pdf --namespace guides --replace")
