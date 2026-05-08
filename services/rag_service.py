import os
import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# Configurable Path
KNOWLEDGE_BASE_PATH = os.environ.get('KNOWLEDGE_BASE_PATH', 'knowladge_base')

class RAGService:
    def __init__(self, knowledge_base_path=KNOWLEDGE_BASE_PATH):
        self.kb_path = knowledge_base_path
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = None
        self.chunks = []
        
        # Initialize only once on startup
        if os.path.exists(self.kb_path):
            print(f"RAG Service: Initializing from {self.kb_path}...")
            self.load_documents()
        else:
            print(f"RAG Service: Knowledge base path {self.kb_path} not found.")

    def load_documents(self):
        """Loads and processes all supported files from the knowledge base."""
        all_text = ""
        for filename in os.listdir(self.kb_path):
            file_path = os.path.join(self.kb_path, filename)
            if filename.endswith('.pdf'):
                all_text += self._extract_text_from_pdf(file_path) + "\n"
            elif filename.endswith('.txt') or filename.endswith('.md'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        all_text += f.read() + "\n"
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
        
        if all_text:
            self.chunks = self._split_chunks(all_text)
            self._create_embeddings()

    def _extract_text_from_pdf(self, file_path):
        text = ""
        try:
            # Use pymupdf (fitz) for better extraction
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
        except Exception as e:
            print(f"Error reading PDF {file_path} with pymupdf: {e}")
        return text

    def _split_chunks(self, text, chunk_size=500, overlap=50):
        chunks = []
        # Basic chunking by characters, could be improved to split by sentences/paragraphs
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    def _create_embeddings(self):
        if not self.chunks:
            return
        
        embeddings = self.model.encode(self.chunks)
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
        print(f"RAG Service: Indexed {len(self.chunks)} chunks.")

    def search(self, query, top_k=3):
        """Searches the vector database for relevant chunks."""
        if self.index is None or not self.chunks:
            return []
        
        query_vector = self.model.encode([query])
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), top_k)
        
        results = []
        for idx in indices[0]:
            if idx != -1:
                results.append(self.chunks[idx])
        return results

# Singleton instance initialized on module load
rag_service = RAGService()
