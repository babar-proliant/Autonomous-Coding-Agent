"""
Vector store for semantic code search using sqlite-vec.
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass
import json

from backend.config import settings, DATA_DIR
from backend.utils import logger


@dataclass
class SearchResult:
    """Result from vector search."""
    id: int
    file_path: str
    symbol_name: str
    symbol_type: str
    code_snippet: str
    distance: float
    metadata: Dict[str, Any] = None


class VectorStore:
    """
    Vector database using sqlite-vec for semantic code search.
    Stores code embeddings for fast similarity search.
    """
    
    _instance: Optional['VectorStore'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.db_path = settings.vector_db_path
            self.embedding_dimension = 384  # all-MiniLM-L6-v2 dimension
            self._connection: Optional[sqlite3.Connection] = None
            self._initialized = False
    
    def initialize(self):
        """Initialize the vector database."""
        if self._initialized:
            return
        
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create connection
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row
        
        # Enable sqlite-vec extension
        try:
            self._connection.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(self._connection)
            logger.info("sqlite-vec extension loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load sqlite-vec extension: {e}")
            logger.info("Will create vector table without extension (limited functionality)")
        
        # Create tables
        self._create_tables()
        
        self._initialized = True
        logger.info(f"Vector store initialized at {self.db_path}")
    
    def _create_tables(self):
        """Create vector storage tables."""
        
        # Code embeddings table (using vec0 virtual table if available)
        try:
            self._connection.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS code_embeddings
                USING vec0(
                    id INTEGER PRIMARY KEY,
                    file_path TEXT,
                    symbol_name TEXT,
                    symbol_type TEXT,
                    code_snippet TEXT,
                    embedding FLOAT[{self.embedding_dimension}]
                )
            """)
            logger.info("Created vec0 virtual table for embeddings")
        except Exception as e:
            logger.warning(f"Could not create vec0 table: {e}")
            # Fallback to regular table
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS code_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT,
                    symbol_name TEXT,
                    symbol_type TEXT,
                    code_snippet TEXT,
                    embedding BLOB
                )
            """)
        
        # Metadata table
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS embedding_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                embedding_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                FOREIGN KEY (embedding_id) REFERENCES code_embeddings(id)
            )
        """)
        
        self._connection.commit()
    
    def add_embedding(
        self,
        file_path: str,
        symbol_name: str,
        symbol_type: str,
        code_snippet: str,
        embedding: np.ndarray,
        metadata: Dict[str, Any] = None
    ) -> int:
        """
        Add a code embedding to the store.
        
        Args:
            file_path: Path to the source file
            symbol_name: Name of the symbol (function, class, etc.)
            symbol_type: Type of symbol (function, class, variable)
            code_snippet: The actual code
            embedding: Embedding vector (numpy array)
            metadata: Optional metadata dictionary
        
        Returns:
            ID of the inserted embedding
        """
        if not self._initialized:
            self.initialize()
        
        # Ensure embedding is the right shape
        embedding = np.array(embedding, dtype=np.float32).flatten()
        if len(embedding) != self.embedding_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                f"got {len(embedding)}"
            )
        
        # Convert to bytes for storage
        embedding_bytes = embedding.tobytes()
        
        cursor = self._connection.execute("""
            INSERT INTO code_embeddings (file_path, symbol_name, symbol_type, code_snippet, embedding)
            VALUES (?, ?, ?, ?, ?)
        """, (file_path, symbol_name, symbol_type, code_snippet, embedding_bytes))
        
        embedding_id = cursor.lastrowid
        
        # Store metadata if provided
        if metadata:
            for key, value in metadata.items():
                self._connection.execute("""
                    INSERT INTO embedding_metadata (embedding_id, key, value)
                    VALUES (?, ?, ?)
                """, (embedding_id, key, json.dumps(value) if not isinstance(value, str) else value))
        
        self._connection.commit()
        return embedding_id
    
    def add_embeddings_batch(
        self,
        embeddings: List[Tuple[str, str, str, str, np.ndarray]]
    ) -> List[int]:
        """
        Add multiple embeddings at once.
        
        Args:
            embeddings: List of (file_path, symbol_name, symbol_type, code_snippet, embedding)
        
        Returns:
            List of inserted IDs
        """
        if not self._initialized:
            self.initialize()
        
        ids = []
        for file_path, symbol_name, symbol_type, code_snippet, embedding in embeddings:
            emb_id = self.add_embedding(
                file_path, symbol_name, symbol_type, code_snippet, embedding
            )
            ids.append(emb_id)
        
        return ids
    
    def search(
        self,
        query_embedding: np.ndarray,
        limit: int = 10,
        file_pattern: str = None,
        symbol_type: str = None
    ) -> List[SearchResult]:
        """
        Search for similar code using cosine similarity.
        
        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results
            file_pattern: Optional file path pattern filter
            symbol_type: Optional symbol type filter
        
        Returns:
            List of SearchResult objects
        """
        if not self._initialized:
            self.initialize()
        
        # Ensure query is the right shape
        query_embedding = np.array(query_embedding, dtype=np.float32).flatten()
        if len(query_embedding) != self.embedding_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                f"got {len(query_embedding)}"
            )
        
        query_bytes = query_embedding.tobytes()
        
        # Build query with filters
        base_query = """
            SELECT id, file_path, symbol_name, symbol_type, code_snippet
            FROM code_embeddings
        """
        
        conditions = []
        params = []
        
        if file_pattern:
            conditions.append("file_path LIKE ?")
            params.append(f"%{file_pattern}%")
        
        if symbol_type:
            conditions.append("symbol_type = ?")
            params.append(symbol_type)
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        # Try using vec_distance_cosine if available
        try:
            # Fetch candidates first
            cursor = self._connection.execute(base_query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                # Get embedding for distance calculation
                emb_cursor = self._connection.execute(
                    "SELECT embedding FROM code_embeddings WHERE id = ?", 
                    (row['id'],)
                )
                emb_row = emb_cursor.fetchone()
                if emb_row:
                    stored_embedding = np.frombuffer(emb_row['embedding'], dtype=np.float32)
                    
                    # Calculate cosine similarity
                    dot_product = np.dot(query_embedding, stored_embedding)
                    norm_query = np.linalg.norm(query_embedding)
                    norm_stored = np.linalg.norm(stored_embedding)
                    
                    if norm_query > 0 and norm_stored > 0:
                        similarity = dot_product / (norm_query * norm_stored)
                        distance = 1.0 - similarity  # Convert to distance
                        
                        results.append(SearchResult(
                            id=row['id'],
                            file_path=row['file_path'],
                            symbol_name=row['symbol_name'],
                            symbol_type=row['symbol_type'],
                            code_snippet=row['code_snippet'],
                            distance=distance
                        ))
            
            # Sort by distance and limit
            results.sort(key=lambda x: x.distance)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error during vector search: {e}")
            return []
    
    def delete_by_file(self, file_path: str):
        """Delete all embeddings for a specific file."""
        if not self._initialized:
            self.initialize()
        
        self._connection.execute(
            "DELETE FROM code_embeddings WHERE file_path = ?",
            (file_path,)
        )
        self._connection.commit()
    
    def delete_all(self):
        """Delete all embeddings."""
        if not self._initialized:
            self.initialize()
        
        self._connection.execute("DELETE FROM code_embeddings")
        self._connection.execute("DELETE FROM embedding_metadata")
        self._connection.commit()
    
    def count(self) -> int:
        """Get total number of embeddings."""
        if not self._initialized:
            self.initialize()
        
        cursor = self._connection.execute("SELECT COUNT(*) FROM code_embeddings")
        return cursor.fetchone()[0]
    
    def close(self):
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Vector store connection closed")


# Global vector store instance
vector_store = VectorStore()


__all__ = ["VectorStore", "vector_store", "SearchResult"]
