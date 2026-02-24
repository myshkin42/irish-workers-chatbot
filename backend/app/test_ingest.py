"""
Test ingestion script - validates pipeline with a small subset of documents.

Run from backend folder:
    python -m app.test_ingest
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Verify environment variables
def check_env():
    required = ["OPENAI_API_KEY", "PINECONE_API_KEY"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        return False
    
    index_name = os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot")
    print(f"✅ Environment OK")
    print(f"   PINECONE_INDEX_NAME: {index_name}")
    print(f"   OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')[:20]}...")
    print(f"   PINECONE_API_KEY: {os.getenv('PINECONE_API_KEY')[:10]}...")
    return True


def test_pinecone_connection():
    """Test Pinecone connection and index access"""
    from pinecone import Pinecone
    
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot")
    
    # List indexes
    indexes = [idx.name for idx in pc.list_indexes()]
    print(f"\n📊 Available indexes: {indexes}")
    
    if index_name not in indexes:
        print(f"❌ Index '{index_name}' not found!")
        return False
    
    # Connect to index
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    print(f"✅ Connected to '{index_name}'")
    print(f"   Total vectors: {stats.get('total_vector_count', 0)}")
    print(f"   Namespaces: {list(stats.get('namespaces', {}).keys()) or ['(none)']}")
    return True


def test_openai_embedding():
    """Test OpenAI embedding API"""
    from openai import OpenAI
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    test_text = "Irish employment law protects workers' rights."
    
    try:
        response = client.embeddings.create(
            input=[test_text],
            model="text-embedding-3-small"
        )
        embedding = response.data[0].embedding
        print(f"\n✅ OpenAI embedding OK")
        print(f"   Dimension: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        return True
    except Exception as e:
        print(f"❌ OpenAI embedding failed: {e}")
        return False


def test_pdf_extraction():
    """Test PDF extraction on a sample document"""
    import fitz
    
    # Find a test PDF
    doc_root = Path(__file__).parent.parent.parent / "data" / "documents" / "en"
    pdfs = list(doc_root.rglob("*.pdf"))[:1]
    
    if not pdfs:
        print(f"\n⚠️  No PDFs found in {doc_root}")
        return False
    
    test_pdf = pdfs[0]
    print(f"\n📄 Testing PDF extraction: {test_pdf.name}")
    
    try:
        with fitz.open(str(test_pdf)) as doc:
            text = ""
            page_count = len(doc)
            for page in doc:
                text += page.get_text()
        
        print(f"✅ Extracted {len(text)} characters from {page_count} pages")
        print(f"   First 200 chars: {text[:200].strip()}...")
        return True
    except Exception as e:
        print(f"❌ PDF extraction failed: {e}")
        return False


def test_chunking():
    """Test the chunking logic"""
    from app.ingest import chunk_document, count_tokens
    
    sample_text = """
    Section 1. Short title
    This Act may be cited as the Test Act 2024.
    
    Section 2. Interpretation
    In this Act—
    "employee" means a person who has entered into or works under a contract of employment;
    "employer" means the person with whom the employee has entered into or works under a contract of employment.
    
    Section 3. Rights of employees
    Every employee shall have the right to fair treatment in the workplace. This includes the right to:
    (a) receive payment for work performed,
    (b) reasonable working hours,
    (c) safe working conditions,
    (d) freedom from discrimination.
    
    The employer shall ensure these rights are respected at all times.
    """
    
    chunks = chunk_document(sample_text)
    print(f"\n✅ Chunking OK")
    print(f"   Input: {count_tokens(sample_text)} tokens")
    print(f"   Output: {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"   Chunk {i}: {count_tokens(chunk)} tokens")
    return True


def test_full_pipeline():
    """Test full pipeline on 2 documents"""
    from app.ingest import (
        extract_text, chunk_document, get_metadata, 
        embed_all, make_safe_id, file_hash, count_tokens
    )
    from pinecone import Pinecone
    
    doc_root = Path(__file__).parent.parent.parent / "data" / "documents" / "en"
    
    # Get 2 test files from different folders
    test_files = []
    for folder in ["guides", "codes"]:
        folder_path = doc_root / folder
        if folder_path.exists():
            pdfs = list(folder_path.glob("*.pdf"))[:1]
            test_files.extend(pdfs)
    
    if len(test_files) < 2:
        # Fallback to any PDFs
        test_files = list(doc_root.rglob("*.pdf"))[:2]
    
    print(f"\n🧪 Testing full pipeline on {len(test_files)} documents...")
    
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot"))
    
    total_vectors = 0
    
    for filepath in test_files:
        print(f"\n   Processing: {filepath.name}")
        
        # Extract
        text = extract_text(filepath)
        if not text:
            print(f"   ⚠️  Empty text")
            continue
        print(f"   Extracted: {len(text)} chars")
        
        # Chunk
        chunks = chunk_document(text)
        print(f"   Chunks: {len(chunks)}")
        
        # Embed
        embeddings = embed_all(chunks[:5])  # Only embed first 5 chunks for test
        print(f"   Embeddings: {len(embeddings)} x {len(embeddings[0])} dims")
        
        # Prepare vectors
        base_meta = get_metadata(filepath, doc_root)
        namespace = base_meta.pop("namespace")
        fhash = file_hash(filepath)
        base_id = make_safe_id(f"TEST-{filepath.stem}-{fhash}")
        
        vectors = []
        for i, (chunk, embedding) in enumerate(zip(chunks[:5], embeddings)):
            meta = {
                **base_meta,
                "text": chunk,
                "chunk_index": i,
                "token_count": count_tokens(chunk),
            }
            meta = {k: v for k, v in meta.items() if v is not None}
            
            vectors.append({
                "id": f"{base_id}-{i}",
                "values": embedding,
                "metadata": meta
            })
        
        # Upsert
        index.upsert(vectors=vectors, namespace=f"test-{namespace}")
        total_vectors += len(vectors)
        print(f"   ✅ Upserted {len(vectors)} vectors to namespace 'test-{namespace}'")
    
    # Verify
    import time
    time.sleep(2)  # Give Pinecone a moment
    stats = index.describe_index_stats()
    print(f"\n📊 Index stats after test:")
    print(f"   Total vectors: {stats.get('total_vector_count', 0)}")
    for ns, info in stats.get("namespaces", {}).items():
        print(f"   {ns}: {info.get('vector_count', 0)} vectors")
    
    return total_vectors > 0


def cleanup_test_vectors():
    """Remove test vectors"""
    from pinecone import Pinecone
    
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot"))
    
    stats = index.describe_index_stats()
    test_namespaces = [ns for ns in stats.get("namespaces", {}).keys() if ns.startswith("test-")]
    
    if test_namespaces:
        print(f"\n🧹 Cleaning up test namespaces: {test_namespaces}")
        for ns in test_namespaces:
            index.delete(delete_all=True, namespace=ns)
        print("   ✅ Cleaned up")
    else:
        print("\n🧹 No test namespaces to clean up")


if __name__ == "__main__":
    print("=" * 60)
    print("Irish Workers Chatbot - Ingestion Pipeline Test")
    print("=" * 60)
    
    # Run checks
    if not check_env():
        sys.exit(1)
    
    if not test_pinecone_connection():
        sys.exit(1)
    
    if not test_openai_embedding():
        sys.exit(1)
    
    if not test_pdf_extraction():
        sys.exit(1)
    
    if not test_chunking():
        sys.exit(1)
    
    # Full pipeline test
    if not test_full_pipeline():
        print("\n❌ Full pipeline test failed")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    
    # Ask about cleanup
    response = input("\nClean up test vectors? [y/N]: ").strip().lower()
    if response == 'y':
        cleanup_test_vectors()
    else:
        print("Test vectors left in place (in test-* namespaces)")
    
    print("\n🚀 Ready for full ingestion. Run:")
    print("   python -m app.ingest ../data/documents/en")
