"""
Database management for the Autonomous Coding Agent.
Uses SQLite with aiosqlite for async operations.
"""

import asyncio
import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import json

from backend.config import settings, DATA_DIR
from backend.utils import logger


class Database:
    """Async SQLite database manager."""
    
    _instance: Optional['Database'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.db_path = settings.database_path
            self._connection: Optional[aiosqlite.Connection] = None
            self._initialized = True
    
    async def initialize(self):
        """Initialize the database and create tables."""
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        async with self._lock:
            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row
            
            # Enable foreign keys
            await self._connection.execute("PRAGMA foreign_keys = ON")
            
            # Create tables
            await self._create_tables()
            
            logger.info(f"Database initialized at {self.db_path}")
    
    async def close(self):
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection as context manager."""
        if not self._connection:
            await self.initialize()
        yield self._connection
    
    async def _create_tables(self):
        """Create all database tables."""
        
        # Sessions table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_path TEXT,
                project_name TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # Messages table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                importance_score REAL DEFAULT 0.5,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # Create index for session queries
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session 
            ON messages(session_id)
        """)
        
        # Tasks table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                parent_task_id TEXT,
                agent_name TEXT,
                description TEXT NOT NULL,
                task_type TEXT,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                dependencies TEXT,
                result TEXT,
                error TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (parent_task_id) REFERENCES tasks(id)
            )
        """)
        
        # Task edges table (for DAG)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS task_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                from_task_id TEXT NOT NULL,
                to_task_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (from_task_id) REFERENCES tasks(id),
                FOREIGN KEY (to_task_id) REFERENCES tasks(id)
            )
        """)
        
        # Failed attempts table (for learning)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS failed_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                approach TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                stack_trace TEXT,
                solution TEXT,
                lessons_learned TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)
        
        # Project knowledge table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS project_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                project_path TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                key_name TEXT NOT NULL,
                key_value TEXT NOT NULL,
                embedding_id INTEGER,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # File index table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS file_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_extension TEXT,
                file_size INTEGER,
                content_hash TEXT,
                language TEXT,
                last_modified TIMESTAMP,
                is_indexed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # Symbol index table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS symbol_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                symbol_type TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                full_name TEXT,
                signature TEXT,
                docstring TEXT,
                line_start INTEGER,
                line_end INTEGER,
                embedding_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES file_index(id)
            )
        """)
        
        # Create indexes for symbol search
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_name 
            ON symbol_index(symbol_name)
        """)
        
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_type 
            ON symbol_index(symbol_type)
        """)
        
        # Dependencies table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                source_file TEXT NOT NULL,
                target_file TEXT NOT NULL,
                dependency_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # Checkpoints table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                description TEXT,
                checkpoint_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # File states table (for checkpoint contents)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS file_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_compressed BLOB,
                original_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(id)
            )
        """)
        
        # Tool executions table (audit log)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                task_id TEXT,
                tool_name TEXT NOT NULL,
                parameters TEXT,
                result TEXT,
                status TEXT,
                error_message TEXT,
                execution_time_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)
        
        # Agent activity log table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS agent_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # Model usage table (resource tracking)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS model_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                tokens_input INTEGER,
                tokens_output INTEGER,
                inference_time_ms INTEGER,
                vram_used_gb REAL,
                task_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # Settings table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await self._connection.commit()
        logger.info("Database tables created successfully")
    
    async def execute(self, query: str, params: tuple = None):
        """Execute a SQL query."""
        async with self.get_connection() as conn:
            await conn.execute(query, params or ())
            await conn.commit()
    
    async def execute_many(self, query: str, params_list: List[tuple]):
        """Execute multiple SQL queries."""
        async with self.get_connection() as conn:
            await conn.executemany(query, params_list)
            await conn.commit()
    
    async def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Fetch a single row."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Fetch all rows."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row into a table."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = tuple(data.values())
        
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, values)
            await conn.commit()
            return cursor.lastrowid
    
    async def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple = None):
        """Update rows in a table."""
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        values = tuple(data.values()) + (where_params or ())
        
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        
        async with self.get_connection() as conn:
            await conn.execute(query, values)
            await conn.commit()
    
    async def delete(self, table: str, where: str, params: tuple = None):
        """Delete rows from a table."""
        query = f"DELETE FROM {table} WHERE {where}"
        
        async with self.get_connection() as conn:
            await conn.execute(query, params or ())
            await conn.commit()


# Global database instance
db = Database()


__all__ = ["Database", "db"]
