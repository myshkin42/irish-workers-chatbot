"""
Irish Workers' Rights Chatbot - Document Ingestion

Simplified ingestion pipeline for Irish employment law documents.
No state routing needed (single jurisdiction), simpler metadata.

Usage:
    python -m app.ingest ../data/documents/en
"""
import os
import re
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional

from dotenv import load_dotenv
from tqdm import tqdm
import fitz  # PyMuPDF
import tiktoken
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

# Chunking settings
TARGET_TOKENS = 400
OVERLAP_TOKENS = 50
MAX_TOKENS = 8000

# Initialize tokenizer
try:
    tokenizer = tiktoken.encoding_for_model(EMBED_MODEL)
except:
    tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text))

# Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)

# ----------------------------------------------------------------------------
# Text Extraction
# ----------------------------------------------------------------------------
def extract_text_pdf(filepath: str) -> str:
    """Extract text from PDF"""
    text_parts = []
    try:
        with fitz.open(filepath) as doc:
            for page in doc:
                text_parts.append(page.get_text())
    except Exception as e:
        print(f"[PDF ERROR] {filepath}: {e}")
    return "\n".join(text_parts).strip()


def extract_text_md(filepath: str) -> str:
    """Extract text from Markdown"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[MD ERROR] {filepath}: {e}")
        return ""


def extract_text(filepath: Path) -> str:
    """Extract text based on file type"""
    ext = filepath.suffix.lower()
    if ext == ".pdf":
        return extract_text_pdf(str(filepath))
    elif ext in (".md", ".txt"):
        return extract_text_md(str(filepath))
    else:
        print(f"[SKIP] Unsupported file type: {filepath}")
        return ""


# ----------------------------------------------------------------------------
# Text Processing
# ----------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """Clean and normalize text"""
    # Remove hyphenation at line breaks
    text = re.sub(r'-\s*\n\s*', '', text)
    # Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Section heading patterns for Irish legal documents
SECTION_PATTERN = re.compile(
    r'(?im)^(?:section|part|chapter|article|regulation|clause)\s+[A-Za-z0-9\-\.]+.*$'
)


def split_by_sections(text: str) -> List[str]:
    """Split text by section headings"""
    lines = text.splitlines()
    blocks = []
    current_block = []
    
    for line in lines:
        if SECTION_PATTERN.match(line) and current_block:
            blocks.append("\n".join(current_block).strip())
            current_block = [line]
        else:
            current_block.append(line)
    
    if current_block:
        blocks.append("\n".join(current_block).strip())
    
    return [b for b in blocks if b.strip()] or [text]


def chunk_by_tokens(text: str, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS) -> List[str]:
    """Split text into token-based chunks with overlap"""
    tokens = tokenizer.encode(text)
    chunks = []
    step = max(1, target - overlap)
    
    for start in range(0, len(tokens), step):
        chunk_tokens = tokens[start:start + target]
        if chunk_tokens:
            chunks.append(tokenizer.decode(chunk_tokens))
    
    return chunks


def chunk_document(text: str) -> List[str]:
    """Create chunks from document text"""
    text = clean_text(text)
    sections = split_by_sections(text)
    
    all_chunks = []
    for section in sections:
        first_line = section.split("\n", 1)[0].strip()
        
        for chunk in chunk_by_tokens(section):
            # Prepend section heading if not already there
            if first_line and not chunk.startswith(first_line):
                chunk = f"{first_line}\n{chunk}"
            
            token_count = count_tokens(chunk)
            if 20 <= token_count <= MAX_TOKENS:
                all_chunks.append(chunk)
    
    return all_chunks


# ----------------------------------------------------------------------------
# Metadata Extraction
# ----------------------------------------------------------------------------
def extract_section_id(text: str) -> Optional[str]:
    """Extract section identifier from text"""
    first_line = text.split("\n", 1)[0].strip()
    
    patterns = [
        (r'(?i)^section\s+([0-9A-Za-z\-\.]+)', 'section'),
        (r'(?i)^part\s+([0-9A-Za-z\-\.]+)', 'part'),
        (r'(?i)^chapter\s+([0-9A-Za-z\-\.]+)', 'chapter'),
        (r'(?i)^article\s+([0-9A-Za-z\-\.]+)', 'article'),
        (r'(?i)^regulation\s+([0-9A-Za-z\-\.]+)', 'regulation'),
        (r'(?i)^clause\s+([0-9A-Za-z\-\.]+)', 'clause'),
    ]
    
    for pattern, prefix in patterns:
        match = re.search(pattern, first_line)
        if match:
            return f"{prefix} {match.group(1)}"
    
    return None


def get_namespace(filepath: Path, doc_root: Path) -> str:
    """Determine namespace from file path"""
    try:
        rel_parts = filepath.relative_to(doc_root).parts
    except ValueError:
        return "unknown"
    
    if not rel_parts:
        return "unknown"
    
    # Skip language folder (en/ga) if present
    if rel_parts[0] in ("en", "ga"):
        if len(rel_parts) > 1:
            return rel_parts[1].lower()
        return "unknown"
    
    return rel_parts[0].lower()


def extract_year(text: str) -> Optional[int]:
    """Extract year from filename or text"""
    match = re.search(r'(19|20)\d{2}', text)
    return int(match.group()) if match else None


def make_display_name(filepath: Path) -> str:
    """Create human-readable display name from filename"""
    name = filepath.stem
    # Remove common suffixes
    name = re.sub(r'-\d{4}$', '', name)  # Remove year suffix
    name = re.sub(r'-s-i-\d+.*$', '', name, flags=re.I)  # Remove S.I. references
    # Convert to title case
    name = name.replace("-", " ").replace("_", " ")
    name = " ".join(word.capitalize() for word in name.split())
    return name


def get_metadata(filepath: Path, doc_root: Path) -> Dict:
    """Extract metadata from file"""
    stem = filepath.stem.lower()
    
    # Determine document type from path
    namespace = get_namespace(filepath, doc_root)
    
    # Map namespace to doc_type
    doc_type_map = {
        "acts": "legislation",
        "statutory-instruments": "regulation", 
        "codes": "code_of_practice",
        "guides": "guide",
        "procedures": "procedure",
        "sectors": "sector_order",
        "unions": "union_info",
        "eu": "eu_directive"
    }
    doc_type = doc_type_map.get(namespace, "other")
    
    # Detect specific document types
    if "employment-regulation-order" in stem or "ero" in stem:
        doc_type = "ero"
    elif "sectoral-employment-order" in stem or "seo" in stem:
        doc_type = "seo"
    elif "code-of-practice" in stem:
        doc_type = "code_of_practice"
    
    return {
        "display_name": make_display_name(filepath),
        "doc_type": doc_type,
        "year": extract_year(filepath.stem),
        "source_file": filepath.name,
        "namespace": namespace
    }


def make_safe_id(text: str) -> str:
    """Create ASCII-safe ID for Pinecone"""
    clean = text.encode("ascii", errors="ignore").decode()
    clean = re.sub(r"[^a-zA-Z0-9\-_]", "-", clean)
    clean = re.sub(r"-+", "-", clean).strip("-")
    return clean[:100]  # Limit length


# ----------------------------------------------------------------------------
# Embedding
# ----------------------------------------------------------------------------
def embed_batch(texts: List[str], retries: int = 3) -> List[List[float]]:
    """Embed a batch of texts with retry logic"""
    for attempt in range(retries):
        try:
            response = openai_client.embeddings.create(
                input=texts,
                model=EMBED_MODEL
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"[embed] Retry {attempt + 1}: {e} (waiting {wait}s)")
            time.sleep(wait)


def embed_all(texts: List[str], batch_size: int = 100) -> List[List[float]]:
    """Embed all texts in batches"""
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = embed_batch(batch)
        all_embeddings.extend(embeddings)
    
    return all_embeddings


# ----------------------------------------------------------------------------
# Ingestion
# ----------------------------------------------------------------------------
def find_documents(root: Path) -> List[Path]:
    """Find all documents to ingest"""
    docs = []
    for ext in ("*.pdf", "*.md", "*.txt"):
        docs.extend(root.rglob(ext))
    return sorted(docs)


def file_hash(filepath: Path) -> str:
    """Generate short hash of file contents"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def ingest_documents(doc_folder: str):
    """Main ingestion function"""
    doc_root = Path(doc_folder).resolve()
    files = find_documents(doc_root)
    
    print(f"📄 Found {len(files)} documents to ingest")
    
    # Ensure index exists
    existing_indexes = {idx.name for idx in pc.list_indexes()}
    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f"Creating index '{PINECONE_INDEX_NAME}'...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=PINECONE_REGION)
        )
        # Wait for index to be ready
        time.sleep(10)
    
    index = pc.Index(PINECONE_INDEX_NAME)
    
    total_vectors = 0
    
    for filepath in tqdm(files, desc="📚 Ingesting"):
        # Extract text
        text = extract_text(filepath)
        if not text:
            print(f"⚠️  Empty: {filepath.name}")
            continue
        
        # Create chunks
        chunks = chunk_document(text)
        if not chunks:
            print(f"⚠️  No chunks: {filepath.name}")
            continue
        
        # Get embeddings
        embeddings = embed_all(chunks)
        
        # Prepare metadata
        base_meta = get_metadata(filepath, doc_root)
        namespace = base_meta.pop("namespace")
        fhash = file_hash(filepath)
        base_id = make_safe_id(f"{filepath.stem}-{fhash}")
        
        # Create vectors
        vectors = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            section_id = extract_section_id(chunk)
            
            meta = {
                **base_meta,
                "text": chunk,
                "chunk_index": i,
                "token_count": count_tokens(chunk),
            }
            if section_id:
                meta["section_id"] = section_id
            
            # Remove None values
            meta = {k: v for k, v in meta.items() if v is not None}
            
            vectors.append({
                "id": f"{base_id}-{i}",
                "values": embedding,
                "metadata": meta
            })
        
        # Upsert to Pinecone
        for batch_start in range(0, len(vectors), 100):
            batch = vectors[batch_start:batch_start + 100]
            index.upsert(vectors=batch, namespace=namespace)
        
        total_vectors += len(vectors)
        print(f"✅ {filepath.name}: {len(vectors)} vectors → {namespace}")
    
    print(f"\n🎉 Ingestion complete! Total vectors: {total_vectors}")
    
    # Print summary
    stats = index.describe_index_stats()
    print("\n📊 Index summary:")
    for ns, info in stats.get("namespaces", {}).items():
        print(f"  {ns}: {info.get('vector_count', 0)} vectors")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m app.ingest <document_folder>")
        print("Example: python -m app.ingest ../data/documents/en")
        sys.exit(1)
    
    folder = sys.argv[1]
    if not Path(folder).exists():
        print(f"Error: Folder not found: {folder}")
        sys.exit(1)
    
    ingest_documents(folder)
