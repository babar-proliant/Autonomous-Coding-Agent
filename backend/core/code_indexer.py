"""
Code Indexing Engine for semantic code search and understanding.
Uses tree-sitter for parsing and embeddings for semantic search.
"""

import asyncio
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from enum import Enum
import hashlib
import re

from backend.config import settings
from backend.utils import logger, AgentLogger
from backend.memory.vector_store import vector_store, SearchResult


class SymbolType(str, Enum):
    """Types of code symbols."""
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"
    STRUCT = "struct"
    MODULE = "module"


@dataclass
class CodeSymbol:
    """A symbol extracted from code."""
    name: str
    full_name: str  # Includes class/module prefix
    symbol_type: SymbolType
    file_path: str
    line_start: int
    line_end: int
    signature: str = ""
    docstring: str = ""
    code_snippet: str = ""
    parent_symbol: Optional[str] = None
    embedding_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileIndex:
    """Index of a single file."""
    file_path: str
    language: str
    symbols: List[CodeSymbol]
    imports: List[str]
    exports: List[str]
    content_hash: str
    last_indexed: datetime
    error: Optional[str] = None


class CodeIndexer:
    """
    Indexes code files for semantic search and understanding.
    
    Features:
    - Multi-language support via tree-sitter
    - Symbol extraction (classes, functions, etc.)
    - Embedding generation for semantic search
    - Incremental indexing
    """
    
    # Language detection by extension
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "c_sharp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
    }
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id
        self._logger = AgentLogger("CodeIndexer", session_id)
        self._parsers: Dict[str, Any] = {}
        self._embedding_model = None
        self._indexed_files: Dict[str, FileIndex] = {}
    
    def _get_parser(self, language: str):
        """Get or create a tree-sitter parser for a language."""
        if language in self._parsers:
            return self._parsers[language]
        
        try:
            import tree_sitter_python
            from tree_sitter import Language, Parser
            
            if language == "python":
                lang_module = tree_sitter_python
            elif language == "javascript":
                import tree_sitter_javascript
                lang_module = tree_sitter_javascript
            elif language == "typescript":
                import tree_sitter_typescript
                lang_module = tree_sitter_typescript
            else:
                self._logger.warning(f"No tree-sitter grammar for: {language}")
                return None
            
            parser = Parser(Language(lang_module.language()))
            self._parsers[language] = parser
            return parser
            
        except ImportError as e:
            self._logger.warning(f"Could not load tree-sitter for {language}: {e}")
            return None
    
    async def _get_embedding_model(self):
        """Get or create the embedding model."""
        if self._embedding_model is not None:
            return self._embedding_model
        
        try:
            from sentence_transformers import SentenceTransformer
            
            def load_model():
                return SentenceTransformer(settings.embedding_model_name)
            
            loop = asyncio.get_event_loop()
            self._embedding_model = await loop.run_in_executor(None, load_model)
            
            self._logger.info(f"Loaded embedding model: {settings.embedding_model_name}")
            return self._embedding_model
            
        except ImportError:
            self._logger.warning("sentence-transformers not installed, skipping embeddings")
            return None
    
    def detect_language(self, file_path: Path) -> Optional[str]:
        """Detect language from file extension."""
        return self.LANGUAGE_MAP.get(file_path.suffix.lower())
    
    def should_index(self, file_path: Path) -> bool:
        """Check if a file should be indexed."""
        # Check extension
        if file_path.suffix.lower() not in self.LANGUAGE_MAP:
            return False
        
        # Check against skip patterns
        file_str = str(file_path)
        for pattern in settings.index_skip_patterns:
            if pattern.startswith("*."):
                if file_str.endswith(pattern[1:]):
                    return False
            elif pattern in file_str:
                return False
        
        # Check against include patterns
        for pattern in settings.index_file_patterns:
            if file_path.match(pattern):
                return True
        
        return True
    
    async def index_file(
        self,
        file_path: Path,
        content: str = None
    ) -> Optional[FileIndex]:
        """
        Index a single file.
        
        Args:
            file_path: Path to the file
            content: Optional pre-loaded content
            
        Returns:
            FileIndex or None if indexing failed
        """
        language = self.detect_language(file_path)
        if not language:
            return None
        
        try:
            # Read content if not provided
            if content is None:
                content = file_path.read_text(encoding='utf-8', errors='replace')
            
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            # Check if already indexed with same hash
            if str(file_path) in self._indexed_files:
                existing = self._indexed_files[str(file_path)]
                if existing.content_hash == content_hash:
                    return existing
            
            # Parse with tree-sitter
            parser = self._get_parser(language)
            symbols = []
            
            if parser:
                tree = parser.parse(content.encode())
                symbols = self._extract_symbols(tree.root_node, content, str(file_path), language)
            
            # Extract imports/exports with regex fallback
            imports, exports = self._extract_imports_exports(content, language)
            
            # Create index
            file_index = FileIndex(
                file_path=str(file_path),
                language=language,
                symbols=symbols,
                imports=imports,
                exports=exports,
                content_hash=content_hash,
                last_indexed=datetime.utcnow()
            )
            
            # Generate embeddings
            if symbols:
                await self._generate_embeddings(symbols, content)
            
            self._indexed_files[str(file_path)] = file_index
            self._logger.debug(f"Indexed: {file_path} ({len(symbols)} symbols)")
            
            return file_index
            
        except Exception as e:
            self._logger.error(f"Failed to index {file_path}: {e}")
            return FileIndex(
                file_path=str(file_path),
                language=language,
                symbols=[],
                imports=[],
                exports=[],
                content_hash="",
                last_indexed=datetime.utcnow(),
                error=str(e)
            )
    
    def _extract_symbols(
        self,
        node,
        content: str,
        file_path: str,
        language: str
    ) -> List[CodeSymbol]:
        """Extract symbols from a tree-sitter AST."""
        symbols = []
        
        # Node types for each language
        function_types = {
            "python": ["function_definition", "async_function_definition"],
            "javascript": ["function_declaration", "function_expression", "arrow_function", "method_definition"],
            "typescript": ["function_declaration", "function_expression", "arrow_function", "method_definition", "function_signature"],
            "java": ["method_declaration", "constructor_declaration"],
            "go": ["function_declaration", "method_declaration"],
            "rust": ["function_item"],
        }
        
        class_types = {
            "python": ["class_definition"],
            "javascript": ["class_declaration"],
            "typescript": ["class_declaration", "interface_declaration", "type_alias_declaration"],
            "java": ["class_declaration", "interface_declaration"],
            "go": ["type_declaration"],
            "rust": ["struct_item", "enum_item", "trait_item"],
        }
        
        func_types = function_types.get(language, [])
        cls_types = class_types.get(language, [])
        
        def visit_node(node, parent_name: str = None):
            node_type = node.type
            
            # Extract function/method
            if node_type in func_types:
                symbol = self._create_symbol(
                    node, content, file_path, 
                    SymbolType.METHOD if parent_name else SymbolType.FUNCTION,
                    parent_name
                )
                if symbol:
                    symbols.append(symbol)
            
            # Extract class
            elif node_type in cls_types:
                symbol = self._create_symbol(
                    node, content, file_path, SymbolType.CLASS, None
                )
                if symbol:
                    symbols.append(symbol)
                    # Update parent for nested symbols
                    parent_name = symbol.name
            
            # Recurse into children
            for child in node.children:
                visit_node(child, parent_name)
        
        visit_node(node)
        return symbols
    
    def _create_symbol(
        self,
        node,
        content: str,
        file_path: str,
        symbol_type: SymbolType,
        parent_name: str = None
    ) -> Optional[CodeSymbol]:
        """Create a symbol from a tree-sitter node."""
        # Get name from first identifier child
        name = None
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                name = content[child.start_byte:child.end_byte]
                break
        
        if not name:
            return None
        
        # Get code snippet
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        lines = content.splitlines()
        snippet = "\n".join(lines[max(0, start_line-1):min(len(lines), end_line)])
        
        # Build full name
        full_name = f"{parent_name}.{name}" if parent_name else name
        
        return CodeSymbol(
            name=name,
            full_name=full_name,
            symbol_type=symbol_type,
            file_path=file_path,
            line_start=start_line,
            line_end=end_line,
            code_snippet=snippet[:1000],  # Limit snippet size
            parent_symbol=parent_name
        )
    
    def _extract_imports_exports(
        self,
        content: str,
        language: str
    ) -> Tuple[List[str], List[str]]:
        """Extract imports and exports using regex."""
        imports = []
        exports = []
        
        if language == "python":
            # Python imports
            import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+(.+)$'
            for match in re.finditer(import_pattern, content, re.MULTILINE):
                module = match.group(1) or ""
                names = match.group(2)
                imports.append(f"{module}.{names}" if module else names)
        
        elif language in ("javascript", "typescript"):
            # ES6 imports
            import_pattern = r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]'
            for match in re.finditer(import_pattern, content):
                imports.append(match.group(1))
            
            # Exports
            export_pattern = r'export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)'
            for match in re.finditer(export_pattern, content):
                exports.append(match.group(1))
        
        elif language == "java":
            import_pattern = r'import\s+([\w.]+);'
            for match in re.finditer(import_pattern, content):
                imports.append(match.group(1))
        
        elif language == "go":
            import_pattern = r'import\s+(?:\(([^)]+)\)|"([^"]+)")'
            for match in re.finditer(import_pattern, content, re.DOTALL):
                if match.group(1):
                    for imp in re.findall(r'"([^"]+)"', match.group(1)):
                        imports.append(imp)
                elif match.group(2):
                    imports.append(match.group(2))
        
        return imports, exports
    
    async def _generate_embeddings(
        self,
        symbols: List[CodeSymbol],
        content: str
    ):
        """Generate and store embeddings for symbols."""
        model = await self._get_embedding_model()
        if not model:
            return
        
        try:
            # Prepare texts for embedding
            texts = []
            for symbol in symbols:
                text = f"{symbol.symbol_type.value} {symbol.full_name}\n{symbol.code_snippet}"
                if symbol.docstring:
                    text += f"\n{symbol.docstring}"
                texts.append(text)
            
            # Generate embeddings
            def encode():
                return model.encode(texts, show_progress_bar=False)
            
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, encode)
            
            # Store in vector database
            for symbol, embedding in zip(symbols, embeddings):
                try:
                    embedding_id = vector_store.add_embedding(
                        file_path=symbol.file_path,
                        symbol_name=symbol.full_name,
                        symbol_type=symbol.symbol_type.value,
                        code_snippet=symbol.code_snippet,
                        embedding=embedding,
                        metadata={
                            "line_start": symbol.line_start,
                            "line_end": symbol.line_end
                        }
                    )
                    symbol.embedding_id = embedding_id
                    
                except Exception as e:
                    self._logger.warning(f"Failed to store embedding: {e}")
            
            self._logger.debug(f"Generated {len(symbols)} embeddings")
            
        except Exception as e:
            self._logger.error(f"Failed to generate embeddings: {e}")
    
    async def index_directory(
        self,
        directory: Path,
        recursive: bool = True
    ) -> Dict[str, Any]:
        """
        Index all files in a directory.
        
        Args:
            directory: Directory to index
            recursive: Whether to index subdirectories
            
        Returns:
            Summary of indexing
        """
        indexed = 0
        failed = 0
        skipped = 0
        total_symbols = 0
        
        patterns = settings.index_file_patterns
        
        # Find all matching files
        files = []
        for pattern in patterns:
            if recursive:
                files.extend(directory.rglob(pattern))
            else:
                files.extend(directory.glob(pattern))
        
        # Index each file
        for file_path in files:
            if not self.should_index(file_path):
                skipped += 1
                continue
            
            result = await self.index_file(file_path)
            
            if result:
                indexed += 1
                total_symbols += len(result.symbols)
                if result.error:
                    failed += 1
            else:
                failed += 1
        
        summary = {
            "indexed": indexed,
            "failed": failed,
            "skipped": skipped,
            "total_symbols": total_symbols,
            "total_files": len(files)
        }
        
        self._logger.info(f"Directory indexed: {summary}")
        
        return summary
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        symbol_type: SymbolType = None,
        file_pattern: str = None
    ) -> List[Tuple[CodeSymbol, float]]:
        """
        Search for code symbols semantically.
        
        Args:
            query: Search query
            limit: Maximum results
            symbol_type: Filter by symbol type
            file_pattern: Filter by file path pattern
            
        Returns:
            List of (symbol, score) tuples
        """
        model = await self._get_embedding_model()
        if not model:
            # Fallback to text search
            return self._text_search(query, limit)
        
        try:
            # Generate query embedding
            def encode():
                return model.encode([query], show_progress_bar=False)[0]
            
            loop = asyncio.get_event_loop()
            query_embedding = await loop.run_in_executor(None, encode)
            
            # Search vector store
            results = vector_store.search(
                query_embedding,
                limit=limit,
                file_pattern=file_pattern,
                symbol_type=symbol_type.value if symbol_type else None
            )
            
            # Convert to CodeSymbol objects
            symbols = []
            for result in results:
                symbol = CodeSymbol(
                    name=result.symbol_name.split(".")[-1],
                    full_name=result.symbol_name,
                    symbol_type=SymbolType(result.symbol_type),
                    file_path=result.file_path,
                    line_start=0,
                    line_end=0,
                    code_snippet=result.code_snippet,
                    embedding_id=result.id
                )
                symbols.append((symbol, 1.0 - result.distance))
            
            return symbols
            
        except Exception as e:
            self._logger.error(f"Search failed: {e}")
            return self._text_search(query, limit)
    
    def _text_search(
        self,
        query: str,
        limit: int
    ) -> List[Tuple[CodeSymbol, float]]:
        """Fallback text-based search."""
        results = []
        query_lower = query.lower()
        
        for file_index in self._indexed_files.values():
            for symbol in file_index.symbols:
                score = 0.0
                
                if query_lower in symbol.name.lower():
                    score = 0.9
                elif query_lower in symbol.full_name.lower():
                    score = 0.8
                elif query_lower in symbol.code_snippet.lower():
                    score = 0.5
                
                if score > 0:
                    results.append((symbol, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    def get_file_symbols(self, file_path: str) -> List[CodeSymbol]:
        """Get all symbols for a file."""
        file_index = self._indexed_files.get(file_path)
        return file_index.symbols if file_index else []
    
    def get_symbol(self, symbol_name: str) -> Optional[CodeSymbol]:
        """Find a symbol by name."""
        for file_index in self._indexed_files.values():
            for symbol in file_index.symbols:
                if symbol.full_name == symbol_name or symbol.name == symbol_name:
                    return symbol
        return None
    
    def get_imports(self, file_path: str) -> List[str]:
        """Get imports for a file."""
        file_index = self._indexed_files.get(file_path)
        return file_index.imports if file_index else []
    
    def find_references(self, symbol_name: str) -> List[CodeSymbol]:
        """Find all references to a symbol."""
        references = []
        
        for file_index in self._indexed_files.values():
            # Check if symbol is imported
            for imp in file_index.imports:
                if symbol_name in imp:
                    for symbol in file_index.symbols:
                        if symbol_name in symbol.code_snippet:
                            references.append(symbol)
                    break
        
        return references


__all__ = [
    "CodeIndexer",
    "CodeSymbol",
    "FileIndex",
    "SymbolType"
]
