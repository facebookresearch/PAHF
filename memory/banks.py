import os
import pickle
import sqlite3
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import faiss
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


class DragonPlusEmbedding:
    """DRAGON+ embedding model for text embeddings.
    
    Uses Facebook's DRAGON+ model which has separate encoders for
    queries and contexts/documents for better retrieval performance.
    Reference: https://huggingface.co/facebook/dragon-plus-query-encoder
    """

    def __init__(
        self,
        query_encoder: str = "facebook/dragon-plus-query-encoder",
        context_encoder: str = "facebook/dragon-plus-context-encoder",
        device: str = None,
    ):
        """Initialize the DRAGON+ embedding client.

        Args:
            query_encoder: HuggingFace model name for query encoding
            context_encoder: HuggingFace model name for context/document encoding
            device: Device to run model on (default: auto-detect cuda/cpu)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        
        # Load query encoder
        self.query_tokenizer = AutoTokenizer.from_pretrained(query_encoder)
        self.query_model = AutoModel.from_pretrained(query_encoder).to(self.device)
        self.query_model.eval()
        
        # Load context encoder
        self.context_tokenizer = AutoTokenizer.from_pretrained(context_encoder)
        self.context_model = AutoModel.from_pretrained(context_encoder).to(self.device)
        self.context_model.eval()

    def _encode(self, texts: List[str], tokenizer, model) -> np.ndarray:
        """Encode texts using the specified tokenizer and model."""
        with torch.no_grad():
            inputs = tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self.device)
            
            outputs = model(**inputs)
            # Use CLS token embedding
            embeddings = outputs.last_hidden_state[:, 0, :]
            # Normalize embeddings
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            
        return embeddings.cpu().numpy()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents using the context encoder.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        embeddings = self._encode(texts, self.context_tokenizer, self.context_model)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text using the query encoder.

        Args:
            text: Query text to embed

        Returns:
            Embedding vector
        """
        embeddings = self._encode([text], self.query_tokenizer, self.query_model)
        return embeddings[0].tolist()


class MemoryBank(ABC):
    """Abstract base class for memory bank implementations"""

    @abstractmethod
    def add(self, text: str) -> None:
        """Add a new document to the memory bank"""
        pass

    @abstractmethod
    def search(self, query: str, top_k: int = 2) -> List[Tuple[float, str]]:
        """Search for similar documents"""
        pass

    @abstractmethod
    def find_similar_memory(self, text: str, threshold: Optional[float] = None) -> Optional[int]:
        """Find the most similar existing memory.
        
        Args:
            text: Query text to find similar memory for
            threshold: Minimum similarity score to consider a match.
                       If None (default), always returns the best match regardless of score.
                       Typical values for normalized embeddings: 0.3-0.5
        """
        pass

    @abstractmethod
    def update_memory(self, memory_id: int, new_text: str) -> None:
        """Update existing memory at given ID"""
        pass

    @abstractmethod
    def get_memory(self, memory_id: int) -> Optional[str]:
        """Get memory text by ID"""
        pass

    @abstractmethod
    def get_all_memories(self) -> List[Tuple[int, str]]:
        """Get all memories with their IDs"""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close/cleanup memory bank resources"""
        pass


class SQLiteMemoryBank(MemoryBank):
    """
    SQLite-based memory bank that stores memories for multiple people in a single database.
    Each memory is associated with a person_id for separation.
    """

    def __init__(
        self,
        db_path: str = "shared_memory_bank.db",
        person_id: str = "",
        embedding_model=None,
    ):
        """
        Initialize memory bank for a specific person.

        Args:
            db_path: Path to the shared SQLite database
            person_id: Unique identifier for this person (e.g., name)
            embedding_model: Optional embedding model
        """
        if person_id is None:
            raise ValueError("person_id is required for MultiPersonSQLiteMemoryBank")

        self.db_path = db_path
        self.person_id = person_id
        self.embeddings = embedding_model or DragonPlusEmbedding()

        # Create directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """Create the docs table with person_id if it doesn't exist"""
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB NOT NULL
            )
        """
        )
        # Create index on person_id for faster queries
        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_person_id ON docs(person_id)
        """
        )
        # Composite index for faster duplicate checks in add()
        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_person_text ON docs(person_id, text)
        """
        )
        self.conn.commit()

    def _embed_with_retry(self, texts, is_query=False, max_retries=8, base_delay=5):
        """
        Wrapper for embedding calls with retry logic for network errors and timeouts.

        Args:
            texts: List of texts to embed or single text for query
            is_query: If True, use embed_query, else embed_documents
            max_retries: Maximum number of retry attempts (default: 8)
            base_delay: Base delay in seconds (will use exponential backoff, default: 5)
        """
        for attempt in range(max_retries):
            try:
                if is_query:
                    return self.embeddings.embed_query(texts)
                else:
                    return self.embeddings.embed_documents(texts)

            except Exception as e:
                error_str = str(e).lower()

                # Check if this is a retryable error
                is_retryable = (
                    "timeout" in error_str
                    or "rate" in error_str
                    or "limit" in error_str
                    or "connection" in error_str
                )

                if is_retryable and attempt < max_retries - 1:
                    wait_time = base_delay * (2**attempt)
                    time.sleep(wait_time)
                else:
                    raise

    def find_similar_memory(self, text: str, threshold: Optional[float] = None) -> Optional[int]:
        """Find the most similar existing memory for this person.
        
        Args:
            text: Query text to find similar memory for
            threshold: Minimum similarity score. If None, always returns best match.
        """
        query_emb = np.array(
            self._embed_with_retry(text, is_query=True), dtype=np.float32
        )

        self.cursor.execute(
            "SELECT id, embedding FROM docs WHERE person_id = ?",
            (self.person_id,),
        )
        rows = self.cursor.fetchall()
        if not rows:
            return None

        doc_ids = [r[0] for r in rows]
        embeddings = np.array(
            [np.frombuffer(r[1], dtype=np.float32) for r in rows]
        )
        scores = embeddings @ query_emb  # Batch dot product via BLAS

        best_idx = np.argmax(scores)
        # If no threshold, always return best match; otherwise filter
        if threshold is None or scores[best_idx] > threshold:
            return doc_ids[best_idx]
        return None

    def update_memory(self, memory_id: int, new_text: str) -> None:
        """Update existing memory at given ID for this person"""
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # Get new embedding
                new_emb = self._embed_with_retry([new_text], is_query=False)[0]
                new_emb_bytes = np.array(new_emb, dtype=np.float32).tobytes()

                # Update the row (with person_id check for safety)
                self.cursor.execute(
                    """
                    UPDATE docs
                    SET text = ?, embedding = ?
                    WHERE id = ? AND person_id = ?
                """,
                    (new_text, new_emb_bytes, memory_id, self.person_id),
                )

                self.conn.commit()
                return  # Success - exit the function

            except Exception as e:
                if attempt < max_retries - 1:
                    # Not the last attempt - wait and retry
                    time.sleep(retry_delay)
                else:
                    # Last attempt failed - let the program continue running
                    return

    def get_all_memories(self) -> List[Tuple[int, str]]:
        """Get all memories with their IDs for this person"""
        self.cursor.execute(
            "SELECT id, text FROM docs WHERE person_id = ?", (self.person_id,)
        )
        return self.cursor.fetchall()

    def add(self, text: str) -> None:
        """Add a new document to the memory bank for this person"""
        # Check if already exists for this person
        self.cursor.execute(
            "SELECT COUNT(*) FROM docs WHERE person_id = ? AND text = ?",
            (self.person_id, text),
        )
        if self.cursor.fetchone()[0] > 0:
            return

        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # Embed and store
                emb = self._embed_with_retry([text], is_query=False)[0]
                emb_bytes = np.array(emb, dtype=np.float32).tobytes()

                self.cursor.execute(
                    "INSERT INTO docs (person_id, text, embedding) VALUES (?, ?, ?)",
                    (self.person_id, text, emb_bytes),
                )
                self.conn.commit()
                return  # Success - exit the function

            except Exception as e:
                if attempt < max_retries - 1:
                    # Not the last attempt - wait and retry
                    time.sleep(retry_delay)
                else:
                    # Last attempt failed - let the program continue running
                    return

    def search(self, query: str, top_k: int = 2) -> List[Tuple[float, str]]:
        """Search for similar documents using dot product similarity for this person"""
        query_emb = np.array(
            self._embed_with_retry(query, is_query=True), dtype=np.float32
        )

        self.cursor.execute(
            "SELECT text, embedding FROM docs WHERE person_id = ?",
            (self.person_id,),
        )
        rows = self.cursor.fetchall()
        if not rows:
            return []

        texts = [r[0] for r in rows]
        embeddings = np.array(
            [np.frombuffer(r[1], dtype=np.float32) for r in rows]
        )
        scores = embeddings @ query_emb  # Batch dot product via BLAS

        # Get top_k indices sorted by score descending
        if len(scores) <= top_k:
            top_indices = np.argsort(scores)[::-1]
        else:
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        return [(float(scores[i]), texts[i]) for i in top_indices]

    def get_memory(self, memory_id: int) -> Optional[str]:
        """Get memory text by ID for this person"""
        self.cursor.execute(
            "SELECT text FROM docs WHERE id = ? AND person_id = ?",
            (memory_id, self.person_id),
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def close(self):
        """Close database connection"""
        self.conn.close()

    @staticmethod
    def get_all_person_ids(db_path: str) -> List[str]:
        """Get all unique person IDs in the database"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT person_id FROM docs")
        person_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return person_ids

    @staticmethod
    def get_person_memory_count(db_path: str, person_id: str) -> int:
        """Get the number of memories for a specific person"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM docs WHERE person_id = ?", (person_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    @staticmethod
    def delete_person_memories(db_path: str, person_id: str) -> None:
        """Delete all memories for a specific person"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM docs WHERE person_id = ?", (person_id,))
        conn.commit()
        conn.close()


class FAISSMemoryBank(MemoryBank):
    """
    FAISS-based memory bank that stores memories for multiple people in shared index files.
    Each memory is associated with a person_id for separation.
    """

    def __init__(
        self,
        embedding_model=None,
        use_dot_product: bool = True,
        persistence_path=None,
        person_id: str = "",
    ):
        """
        Initialize memory bank for a specific person.

        Args:
            embedding_model: Optional embedding model
            use_dot_product: Whether to use dot product similarity (True) or L2 distance (False)
            persistence_path: Path to shared FAISS index files
            person_id: Unique identifier for this person (e.g., name)
        """
        if person_id is None:
            raise ValueError("person_id is required for FAISSMemoryBank")

        self.embeddings = embedding_model or DragonPlusEmbedding()
        self.use_dot_product = use_dot_product
        self.person_id = person_id
        self.documents = []  # Store original texts
        self.person_ids = []  # Store person_id for each document
        self.document_embeddings = (
            []
        )  # Store embeddings separately for similarity search
        self.index = None
        self.dimension = None
        self.next_id = 1
        self.id_to_index = {}  # Map document IDs to list indices
        self.index_to_id = {}  # Map list indices to document IDs

        self.persistence_path = persistence_path

        # Create directory if it doesn't exist
        if self.persistence_path:
            persistence_dir = os.path.dirname(self.persistence_path)
            if persistence_dir and not os.path.exists(persistence_dir):
                os.makedirs(persistence_dir, exist_ok=True)

        # Auto-load if path exists
        if self.persistence_path and os.path.exists(f"{self.persistence_path}.index"):
            self.load_index(self.persistence_path)

    def _embed_with_retry(self, texts, is_query=False, max_retries=5, base_delay=2):
        """
        Wrapper for embedding calls with retry logic for network errors.

        Args:
            texts: List of texts to embed or single text for query
            is_query: If True, use embed_query, else embed_documents
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds (will use exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                if is_query:
                    return self.embeddings.embed_query(texts)
                else:
                    return self.embeddings.embed_documents(texts)

            except Exception as e:
                error_str = str(e).lower()
                is_retryable = (
                    "timeout" in error_str
                    or "rate" in error_str
                    or "limit" in error_str
                    or "connection" in error_str
                )

                if is_retryable and attempt < max_retries - 1:
                    wait_time = base_delay * (2**attempt)
                    time.sleep(wait_time)
                else:
                    raise

    def _initialize_index(self, dimension: int):
        """Initialize FAISS index based on similarity metric"""
        self.dimension = dimension
        if self.use_dot_product:
            self.index = faiss.IndexFlatIP(dimension)  # Inner Product (dot product)
        else:
            self.index = faiss.IndexFlatL2(dimension)  # L2 distance

    def find_similar_memory(self, text: str, threshold: Optional[float] = None) -> Optional[int]:
        """Find the most similar existing memory for this person.
        
        Args:
            text: Query text to find similar memory for
            threshold: Minimum similarity score. If None, always returns best match.
        """
        if len(self.documents) == 0 or self.index is None:
            return None

        query_emb = np.array(
            self._embed_with_retry(text, is_query=True), dtype=np.float32
        )

        query_emb = query_emb.reshape(1, -1)
        if self.use_dot_product:
            faiss.normalize_L2(query_emb)

        # Search more than needed to account for person_id filtering
        best_id = None
        best_score = threshold if threshold is not None else -float('inf')
        k = min(len(self.documents), 50)
        while k <= len(self.documents):
            distances, indices = self.index.search(query_emb, k)

            for distance, idx in zip(distances[0], indices[0]):
                if idx == -1 or idx >= len(self.person_ids):
                    continue
                if self.person_ids[idx] != self.person_id:
                    continue

                score = distance if self.use_dot_product else -distance
                if score > best_score:
                    best_score = score
                    best_id = self.index_to_id.get(idx)

            if best_id is not None or k == len(self.documents):
                break
            k = min(len(self.documents), k * 5)

        return best_id

    def update_memory(self, memory_id: int, new_text: str) -> None:
        """Update existing memory at given ID"""
        if memory_id not in self.id_to_index:
            return

        index = self.id_to_index[memory_id]

        # Get new embedding
        new_emb = np.array(
            self._embed_with_retry([new_text], is_query=False)[0], dtype=np.float32
        )

        # Update the stored data
        self.documents[index] = new_text
        self.document_embeddings[index] = new_emb

        # Rebuild FAISS index with updated embeddings
        if self.index is not None:
            embeddings_array = np.array(self.document_embeddings).astype("float32")
            if self.use_dot_product:
                faiss.normalize_L2(embeddings_array)

            self._initialize_index(self.dimension)
            self.index.add(embeddings_array)

        if hasattr(self, "persistence_path") and self.persistence_path:
            self.save_index(self.persistence_path)

    def get_all_memories(self) -> List[Tuple[int, str]]:
        """Get all memories with their IDs for this person"""
        result = []
        for doc_id, index in self.id_to_index.items():
            if self.person_ids[index] == self.person_id:
            result.append((doc_id, self.documents[index]))
        return result

    def add(self, text: str) -> None:
        """Add a new document to the FAISS index for this person"""
        # Check if already exists for this person
        for i, (doc, pid) in enumerate(zip(self.documents, self.person_ids)):
            if doc == text and pid == self.person_id:
                return

        # Embed the text
        emb = np.array(self._embed_with_retry([text], is_query=False)[0]).astype(
            "float32"
        )

        # Initialize index if this is the first document
        if self.index is None:
            self._initialize_index(len(emb))

        # Store the document, person_id, and embedding
        self.documents.append(text)
        self.person_ids.append(self.person_id)
        self.document_embeddings.append(emb)
        self.id_to_index[self.next_id] = len(self.documents) - 1
        self.index_to_id[len(self.documents) - 1] = self.next_id
        self.next_id += 1

        # Normalize for dot product similarity if needed
        emb_to_add = emb.copy()
        if self.use_dot_product:
            faiss.normalize_L2(emb_to_add.reshape(1, -1))

        # Add to index
        self.index.add(emb_to_add.reshape(1, -1))

        # Auto-save if persistence path is set
        if hasattr(self, "persistence_path") and self.persistence_path:
            self.save_index(self.persistence_path)

    def search(self, query: str, top_k: int = 2) -> List[Tuple[float, str]]:
        """Search for similar documents using FAISS for this person"""
        if self.index is None or len(self.documents) == 0:
            return []

        # Embed query
        query_emb = (
            np.array(self._embed_with_retry(query, is_query=True))
            .astype("float32")
            .reshape(1, -1)
        )

        # Normalize for dot product similarity if needed
        if self.use_dot_product:
            faiss.normalize_L2(query_emb)

        # Search with expanding k to ensure we find enough results for this person
        results = []
        k = min(len(self.documents), max(top_k * 10, 50))
        while k <= len(self.documents):
        distances, indices = self.index.search(query_emb, k)

        # Filter results to only include this person's memories
        results = []
            for distance, idx in zip(distances[0], indices[0]):
                if idx != -1 and idx < len(self.person_ids):
                if self.person_ids[idx] == self.person_id:
                        score = distance if self.use_dot_product else -distance
                    results.append((score, self.documents[idx]))
                    if len(results) >= top_k:
                        break

            if len(results) >= top_k or k == len(self.documents):
                break
            k = min(len(self.documents), k * 5)

        return results

    def get_memory(self, memory_id: int) -> Optional[str]:
        """Get memory text by ID"""
        if memory_id not in self.id_to_index:
            return None
        index = self.id_to_index[memory_id]
        return self.documents[index]

    def close(self):
        """Close/cleanup memory bank (for compatibility with SQLite)"""
        # FAISS doesn't need explicit closing, but we can clear data if needed
        pass

    def save_index(self, filepath: str):
        """Save FAISS index and documents to disk"""
        if self.index is not None:
            faiss.write_index(self.index, f"{filepath}.index")
            with open(f"{filepath}.docs", "wb") as f:
                pickle.dump(
                    {
                        "documents": self.documents,
                        "person_ids": self.person_ids,
                        "document_embeddings": self.document_embeddings,
                        "id_to_index": self.id_to_index,
                        "next_id": self.next_id,
                        "dimension": self.dimension,
                        "use_dot_product": self.use_dot_product,
                    },
                    f,
                )

    def load_index(self, filepath: str):
        """Load FAISS index and documents from disk"""
        self.index = faiss.read_index(f"{filepath}.index")
        with open(f"{filepath}.docs", "rb") as f:
            data = pickle.load(f)
            self.documents = data["documents"]
            self.person_ids = data.get("person_ids", [])  # For backward compatibility
            self.document_embeddings = data["document_embeddings"]
            self.id_to_index = data["id_to_index"]
            self.next_id = data["next_id"]
            self.dimension = data["dimension"]
            self.use_dot_product = data["use_dot_product"]
            # Rebuild reverse map from id_to_index
            self.index_to_id = {idx: doc_id for doc_id, idx in self.id_to_index.items()}
