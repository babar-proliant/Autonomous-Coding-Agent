"""
Coder Agent - Specialized in writing and implementing code.
Streaming version with SSE events.
"""

from typing import Dict, Any
import json
import re

from .base_agent import BaseAgent, AgentState, AgentMessage
from backend.models import model_manager
from backend.tools import ToolRegistry
from backend.memory.working_memory import WorkingMemory
from backend.core import event_bus, EventType
from backend.utils import AgentLogger


class CoderAgent(BaseAgent):
    """
    Specialist agent for writing and implementing code.
    Uses streaming with SSE events.
    """
    
    name = "coder"
    display_name = "Coder Agent"
    description = "Specializes in writing and implementing code"
    preferred_model = "specialist"
    
    def __init__(
        self,
        session_id: str,
        workspace_path: str,
        working_memory: WorkingMemory = None
    ):
        super().__init__(session_id, workspace_path, working_memory)
        self.coder_logger = AgentLogger("Coder", session_id)
    
    def get_system_prompt(self) -> str:
        """System prompt with code-based tool calling."""
        return """You are a code writer. You write code, not plans.

TOOLS (call as Python functions):
- list_all_files() - List files in workspace
- find_file(pattern="*.html") - Find files by pattern
- read_file(file_path="path") - Read a file
- write_file(file_path="path", content="...") - Create/write a file
- edit_file(file_path="path", old_content="...", new_content="...") - Edit a file
- execute_command(command="cmd") - Run shell command

USAGE:
```python
# First, see what exists
list_all_files()

# Write HTML file
write_file(
    file_path="index.html",
    content=\"\"\"<!DOCTYPE html>
<html>
<head><title>Title</title></head>
<body>Content here</body>
</html>\"\"\"
)
```

RULES:
1. START IMMEDIATELY - Write code, don't explain what you'll do
2. Use list_all_files() first to discover workspace
3. Write complete, working files with proper content
4. Use triple quotes for multi-line content
5. No placeholders - use real paths from discovery"""

    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentMessage:
        """Execute a coding task with streaming and iterative tool execution."""
        self.state = AgentState.THINKING
        self.coder_logger.info(f"Task: {task[:50]}...")
        
        MAX_ITERATIONS = 10
        iteration = 0
        all_actions = []
        conversation_history = []
        
        try:
            # Emit thinking start
            await event_bus.emit(
                EventType.THINKING_START,
                self.session_id,
                agent="coder",
                message=f"Working on: {task[:100]}..."
            )
            
            # Initial prompt - direct and action-oriented
            current_prompt = f"""<|im_start|>system
                {self.get_system_prompt()}<|im_end|>
                <|im_start|>user
                Task: {task}

                Write the code now. Use Python function calls to create files.<|im_end|>
                <|im_start|>assistant
                """
            
            while iteration < MAX_ITERATIONS:
                iteration += 1
                self.coder_logger.info(f"=== Iteration {iteration}/{MAX_ITERATIONS} ===")
                
                # Generate with streaming
                full_response = ""
                
                async for chunk in model_manager.generate_stream(
                    current_prompt,
                    model_key="specialist",
                    max_tokens=2048,
                    temperature=0.3,
                    stop=["</s>", "[/INST]"]
                ):
                    full_response += chunk
                    await event_bus.emit(
                        EventType.THINKING_STREAM,
                        self.session_id,
                        agent="coder",
                        content=chunk
                    )
                
                self.coder_logger.info(f"Response length: {len(full_response)}")
                
                # Execute any tool calls - returns (actions, errors)
                actions, tool_errors = await self._execute_tool_calls(full_response)
                all_actions.extend(actions)
                self.coder_logger.info(f"Executed {len(actions)} tool actions in iteration {iteration}")
                
                # Check if we should continue
                if not actions and not tool_errors:
                    self.coder_logger.info("No tools executed - task appears complete")
                    break
                
                # If all actions were successful and no errors, task is likely complete
                # No need to continue iterating
                all_success = all(a.get("success") for a in actions) if actions else False
                if all_success and not tool_errors:
                    self.coder_logger.info("All actions successful - task complete")
                    break
                
                # If there were parsing errors but no actions, we need to tell the model
                if not actions and tool_errors:
                    self.coder_logger.info(f"Got {len(tool_errors)} parsing errors, feeding back to model")
                
                # Build tool results summary for next iteration - INCLUDE ACTUAL RESULTS AND ERRORS
                tool_results = []
                for action in actions:
                    if action.get("success"):
                        result_str = str(action.get("result", ""))[:500]  # Truncate long results
                        tool_results.append(f"✓ {action['tool']}: {result_str}")
                    else:
                        tool_results.append(f"✗ {action['tool']}: {action.get('error', 'Failed')}")
                
                # Add parsing errors to the feedback
                for error in tool_errors:
                    tool_results.append(f"⚠ PARSE ERROR: {error}")
                
                # Continue with tool results - this is crucial for the model to know what happened
                current_prompt = f"""<|im_start|>system
                    {self.get_system_prompt()}<|im_end|>
                    <|im_start|>user
                    Task: {task}

                    Last iteration results:
                    {chr(10).join(tool_results)}

                    Continue - write more code or fix errors. Use Python function calls.<|im_end|>
                    <|im_start|>assistant
                    """
                
                # Emit iteration progress
                await event_bus.emit(
                    EventType.THINKING_STREAM,
                    self.session_id,
                    agent="coder",
                    content=f"\n\n--- Iteration {iteration} complete, {len(actions)} actions taken ---\n\n"
                )
            
            # Compile final summary
            successful_actions = [a for a in all_actions if a.get('success')]
            failed_actions = [a for a in all_actions if not a.get('success')]
            
            summary = f"Completed in {iteration} iterations. "
            summary += f"Actions: {len(successful_actions)} successful, {len(failed_actions)} failed."
            
            # Emit thinking end
            await event_bus.emit(
                EventType.THINKING_END,
                self.session_id,
                agent="coder",
                content=summary,
                metadata={"iterations": iteration, "actions": len(all_actions)}
            )
            
            return self.create_message(
                summary,
                metadata={"task": task, "iterations": iteration, "actions": len(all_actions)}
            )
            
        except Exception as e:
            self.coder_logger.error(e)
            self.state = AgentState.ERROR
            
            await event_bus.emit(
                EventType.ERROR,
                self.session_id,
                agent="coder",
                error=str(e)
            )
            
            return self.create_message(f"Error: {str(e)}", metadata={"status": "error"})
    
    async def _execute_tool_calls(self, response: str) -> tuple:
        """Find and execute tool calls in response using AST parser.
        
        Supports multiple formats:
        1. Python function calls: write_file(file_path="...", content="...")
        2. Code blocks with Python: ```python\nwrite_file(...)\n```
        3. TOOL: format inside code blocks (backward compat)
        4. JSON code blocks (backward compat)
        
        Returns tuple of (actions, errors) so errors can be fed back to model.
        """
        from backend.tools.code_parser import parse_tool_calls
        
        actions = []
        errors = []
        processed_tools = set()
        
        self.coder_logger.info(f"_execute_tool_calls called with response length: {len(response)}")
        
        # Extract code from code blocks first
        code_to_parse = []
        
        # Find all code blocks
        code_block_pattern = r'```(?:python|json|tool)?\s*\n(.*?)\n```'
        code_blocks = re.findall(code_block_pattern, response, re.DOTALL | re.IGNORECASE)
        self.coder_logger.info(f"Found {len(code_blocks)} code blocks")
        
        for block in code_blocks:
            block = block.strip()
            # Skip if it's just a TOOL: prefix - extract the actual call
            if block.startswith("TOOL:"):
                block = block[5:].strip()
            code_to_parse.append(block)
        
        # Also check for raw function calls outside code blocks
        # Match patterns like: tool_name(args) or tool_name(args)
        raw_call_pattern = r'\b(read_file|write_file|edit_file|delete_file|list_directory|create_directory|find_file|list_all_files|search_files|execute_command)\s*\([^)]*\)'
        for match in re.finditer(raw_call_pattern, response):
            # Check if it's inside a code block
            before = response[:match.start()]
            if before.count('```') % 2 == 0:  # Outside code block
                code_to_parse.append(match.group(0))
        
        self.coder_logger.info(f"Parsing {len(code_to_parse)} code segments")
        
        # Parse all code using AST parser
        for code in code_to_parse:
            try:
                tool_calls = parse_tool_calls(code)
                self.coder_logger.info(f"Parsed {len(tool_calls)} tool calls from: {code[:100]}...")
                
                for tool_name, args in tool_calls:
                    # Create unique key
                    args_hash = hash(json.dumps(args, sort_keys=True))
                    tool_key = f"{tool_name}:{args_hash}"
                    
                    if tool_key in processed_tools:
                        continue
                    
                    # Map args to proper format
                    args = self._map_args(tool_name, args)
                    
                    # Run the tool
                    result = await self._run_tool(tool_name, args, actions)
                    if result:
                        processed_tools.add(tool_key)
                        
            except Exception as e:
                self.coder_logger.error(f"Parse error for code: {code[:100]}... - {e}")
                errors.append(f"Could not parse: {code[:50]}... - {str(e)}")
        
        # Fallback: Try JSON patterns for backward compatibility
        if not actions:
            self.coder_logger.info("No actions from AST parser, trying JSON fallback")
            actions, errors = await self._try_json_fallback(response, processed_tools, actions, errors)
        
        self.coder_logger.info(f"Total actions: {len(actions)}, errors: {len(errors)}")
        return actions, errors
    
    async def _try_json_fallback(self, response: str, processed_tools: set, actions: list, errors: list) -> tuple:
        """Fallback to JSON parsing if AST parser finds nothing."""
        # Pattern: JSON with function_name
        fn_pattern = r'"function_name"\s*:\s*"(\w+)"'
        for match in re.finditer(fn_pattern, response):
            tool_name = match.group(1)
            
            json_start = response.rfind('{', 0, match.start())
            if json_start == -1:
                continue
            
            json_end = self._find_matching_brace(response, json_start)
            if json_end == -1:
                continue
            
            json_str = response[json_start:json_end]
            
            try:
                data = json.loads(json_str)
                args = data.get("function_arguments") or data.get("function_arg") or {}
                
                args_hash = hash(json.dumps(args, sort_keys=True))
                tool_key = f"{tool_name}:{args_hash}"
                
                if tool_key not in processed_tools:
                    args = self._map_args(tool_name, args)
                    result = await self._run_tool(tool_name, args, actions)
                    if result:
                        processed_tools.add(tool_key)
            except json.JSONDecodeError:
                pass
            except Exception as e:
                self.coder_logger.error(f"JSON fallback error: {e}")
        
        # Pattern: Direct file_path + content
        if "file_path" in response and "content" in response:
            file_path_pattern = r'"file_path"\s*:\s*"([^"]+)"'
            for match in re.finditer(file_path_pattern, response):
                before = response[:match.start()]
                if before.count('```') % 2 == 1:
                    continue  # Inside code block
                
                json_start = response.rfind('{', 0, match.start())
                if json_start == -1:
                    continue
                
                json_end = self._find_matching_brace(response, json_start)
                if json_end == -1:
                    continue
                
                json_str = response[json_start:json_end]
                
                try:
                    data = json.loads(json_str)
                    if "file_path" in data and "content" in data:
                        tool_name = "write_file"
                        args = {"file_path": data["file_path"], "content": data["content"]}
                        
                        file_key = f"write_file:{args['file_path']}"
                        if file_key not in processed_tools:
                            args = self._map_args(tool_name, args)
                            result = await self._run_tool(tool_name, args, actions)
                            if result:
                                processed_tools.add(file_key)
                except:
                    pass
        
        return actions, errors
    
    def _fix_json_string(self, json_str: str) -> str:
        """Try to fix common JSON issues like unescaped newlines in strings."""
        import re
        
        # Method 1: Replace actual newlines inside string values with escaped newlines
        # This regex finds string values and replaces newlines within them
        def fix_string_content(match):
            content = match.group(1)
            # Replace actual newlines with escaped newlines
            content = content.replace('\n', '\\n')
            # Replace actual tabs with escaped tabs
            content = content.replace('\t', '\\t')
            # Replace actual carriage returns
            content = content.replace('\r', '\\r')
            return '"' + content + '"'
        
        # Match string values (content between quotes)
        # This is a simplified approach - may not handle all edge cases
        fixed = re.sub(r'"([^"]*?)"', fix_string_content, json_str, flags=re.DOTALL)
        
        return fixed
    
    async def _run_tool(self, tool_name: str, args: dict, actions: list) -> bool:
        """Run a tool and emit events."""
        try:
            await event_bus.emit(
                EventType.TOOL_START,
                self.session_id,
                agent="coder",
                tool_name=tool_name,
                args=str(args)[:100]
            )
            
            self.coder_logger.info(f"Executing tool {tool_name} with args: {list(args.keys())}")
            
            result = await self.use_tool(tool_name, **args)
            
            status_val = result.status.value if hasattr(result.status, 'value') else result.status
            success = status_val == "success"
            
            await event_bus.emit(
                EventType.TOOL_RESULT,
                self.session_id,
                agent="coder",
                tool_name=tool_name,
                status="success" if success else "failed",
                result=str(result.result)[:200] if result.result else None,
                error=result.error if not success else None
            )
            
            actions.append({
                "tool": tool_name,
                "success": success,
                "result": str(result.result)[:200] if result.result else None
            })
            return True
        except Exception as e:
            self.coder_logger.error(f"Tool run error: {e}")
            await event_bus.emit(
                EventType.TOOL_ERROR,
                self.session_id,
                agent="coder",
                tool_name=tool_name,
                error=str(e)
            )
            actions.append({"tool": tool_name, "success": False, "error": str(e)})
            return False
    
    def _find_matching_brace(self, s: str, start: int) -> int:
        """Find the index of the closing brace for the opening brace at start."""
        count = 1
        i = start + 1
        in_string = False
        escape_next = False
        
        while i < len(s) and count > 0:
            char = s[i]
            
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == '"' and not escape_next:
                in_string = not in_string
            elif not in_string:
                if char == '{':
                    count += 1
                elif char == '}':
                    count -= 1
            i += 1
        
        return i if count == 0 else -1
    
    def _parse_args(self, tool_name: str, args_str: str) -> dict:
        """Parse tool arguments with smart parameter mapping."""
        args = {}
        
        # Try JSON parse first
        try:
            args = json.loads(args_str)
            args = self._map_args(tool_name, args)
            return args
        except:
            pass
        
        # Parse key="value" patterns
        current_pos = 0
        while current_pos < len(args_str):
            param_match = re.match(r'\s*(\w+)\s*=\s*', args_str[current_pos:])
            if not param_match:
                break
            
            param_name = param_match.group(1)
            current_pos += param_match.end()
            
            if current_pos >= len(args_str):
                break
            
            quote_char = args_str[current_pos]
            if quote_char not in ('"', "'"):
                end_match = re.match(r'([^,\)]*)', args_str[current_pos:])
                if end_match:
                    args[param_name] = end_match.group(1).strip()
                    current_pos += end_match.end() + 1
                continue
            
            current_pos += 1
            value_chars = []
            escape_next = False
            
            while current_pos < len(args_str):
                char = args_str[current_pos]
                
                if escape_next:
                    value_chars.append(char)
                    escape_next = False
                elif char == '\\':
                    escape_next = True
                elif char == quote_char:
                    break
                else:
                    value_chars.append(char)
                
                current_pos += 1
            
            args[param_name] = ''.join(value_chars)
            current_pos += 1
            
            if current_pos < len(args_str) and args_str[current_pos] == ',':
                current_pos += 1
        
        args = self._map_args(tool_name, args)
        return args
    
    def _map_args(self, tool_name: str, args: dict) -> dict:
        """Map generic arg names to proper parameter names."""
        
        if tool_name == "read_file":
            if "arg" in args and "file_path" not in args:
                args["file_path"] = args.pop("arg")
            if "path" in args and "file_path" not in args:
                args["file_path"] = args.pop("path")
            if "filename" in args and "file_path" not in args:
                args["file_path"] = args.pop("filename")
            if "file" in args and "file_path" not in args:
                args["file_path"] = args.pop("file")
            for key in ["rel", "href", "type", "name"]:
                args.pop(key, None)
        
        elif tool_name == "write_file":
            if "arg" in args and "file_path" not in args:
                args["file_path"] = args.pop("arg")
            if "path" in args and "file_path" not in args:
                args["file_path"] = args.pop("path")
            if "filename" in args and "file_path" not in args:
                args["file_path"] = args.pop("filename")
            for key in ["rel", "href", "type", "name"]:
                args.pop(key, None)
        
        elif tool_name == "list_directory":
            if "arg" in args and "dir_path" not in args:
                args["dir_path"] = args.pop("arg")
            if "path" in args and "dir_path" not in args:
                args["dir_path"] = args.pop("path")
            # Default to current directory if no path provided
            if "dir_path" not in args:
                args["dir_path"] = "."
        
        elif tool_name == "edit_file":
            if "arg" in args and "file_path" not in args:
                args["file_path"] = args.pop("arg")
            if "path" in args and "file_path" not in args:
                args["file_path"] = args.pop("path")
            if "filename" in args and "file_path" not in args:
                args["file_path"] = args.pop("filename")
            if "file" in args and "file_path" not in args:
                args["file_path"] = args.pop("file")
            for key in ["rel", "href", "type", "name"]:
                args.pop(key, None)
        
        elif tool_name == "execute_command":
            if "arg" in args and "command" not in args:
                args["command"] = args.pop("arg")
            if "cmd" in args and "command" not in args:
                args["command"] = args.pop("cmd")
        
        elif tool_name == "find_file":
            if "arg" in args and "pattern" not in args:
                args["pattern"] = args.pop("arg")
            if "name" in args and "pattern" not in args:
                args["pattern"] = args.pop("name")
            if "filename" in args and "pattern" not in args:
                args["pattern"] = args.pop("filename")
        
        elif tool_name == "list_all_files":
            if "arg" in args and "extension" not in args:
                args["extension"] = args.pop("arg")
            if "ext" in args and "extension" not in args:
                args["extension"] = args.pop("ext")
        
        return args


class PlannerAgent(BaseAgent):
    """Specialist agent for planning with streaming."""
    
    name = "planner"
    display_name = "Planner Agent"
    description = "Creates implementation plans"
    preferred_model = "specialist"
    
    def get_system_prompt(self) -> str:
        return "You are a planner. Create concise, actionable implementation plans."
    
    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentMessage:
        self.state = AgentState.THINKING
        
        await event_bus.emit(
            EventType.THINKING_START,
            self.session_id,
            agent="planner",
            message="Planning..."
        )
        
        prompt = f"[INST] {self.get_system_prompt()}\n\nTask: {task}\n\nPlan: [/INST]"
        
        full_response = ""
        
        async for chunk in model_manager.generate_stream(
            prompt,
            model_key="specialist",
            max_tokens=512,
            temperature=0.5,
            stop=["</s>", "[/INST]"]
        ):
            full_response += chunk
            await event_bus.emit(
                EventType.THINKING_STREAM,
                self.session_id,
                agent="planner",
                content=chunk
            )
        
        await event_bus.emit(
            EventType.THINKING_END,
            self.session_id,
            agent="planner",
            content=full_response.strip()
        )
        
        return self.create_message(full_response.strip(), metadata={"task": task})


class ReviewerAgent(BaseAgent):
    """Specialist agent for code review with streaming."""
    
    name = "reviewer"
    display_name = "Reviewer Agent"
    description = "Reviews code quality"
    preferred_model = "specialist"
    
    def get_system_prompt(self) -> str:
        return "You are a code reviewer. Check for bugs, security issues, and improvements."
    
    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentMessage:
        self.state = AgentState.THINKING
        
        await event_bus.emit(
            EventType.THINKING_START,
            self.session_id,
            agent="reviewer",
            message="Reviewing..."
        )
        
        prompt = f"[INST] {self.get_system_prompt()}\n\nReview: {task}\n\nFeedback: [/INST]"
        
        full_response = ""
        
        async for chunk in model_manager.generate_stream(
            prompt,
            model_key="specialist",
            max_tokens=512,
            temperature=0.3,
            stop=["</s>", "[/INST]"]
        ):
            full_response += chunk
            await event_bus.emit(
                EventType.THINKING_STREAM,
                self.session_id,
                agent="reviewer",
                content=chunk
            )
        
        await event_bus.emit(
            EventType.THINKING_END,
            self.session_id,
            agent="reviewer",
            content=full_response.strip()
        )
        
        return self.create_message(full_response.strip(), metadata={"task": task})


class DebuggerAgent(BaseAgent):
    """Specialist agent for debugging with streaming."""
    
    name = "debugger"
    display_name = "Debugger Agent"
    description = "Diagnoses and fixes bugs"
    preferred_model = "specialist"
    
    def get_system_prompt(self) -> str:
        return "You are a debugger. Find root causes and provide fixes."
    
    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentMessage:
        self.state = AgentState.THINKING
        
        await event_bus.emit(
            EventType.THINKING_START,
            self.session_id,
            agent="debugger",
            message="Debugging..."
        )
        
        prompt = f"[INST] {self.get_system_prompt()}\n\nIssue: {task}\n\nFix: [/INST]"
        
        full_response = ""
        
        async for chunk in model_manager.generate_stream(
            prompt,
            model_key="specialist",
            max_tokens=512,
            temperature=0.4,
            stop=["</s>", "[/INST]"]
        ):
            full_response += chunk
            await event_bus.emit(
                EventType.THINKING_STREAM,
                self.session_id,
                agent="debugger",
                content=chunk
            )
        
        await event_bus.emit(
            EventType.THINKING_END,
            self.session_id,
            agent="debugger",
            content=full_response.strip()
        )
        
        return self.create_message(full_response.strip(), metadata={"task": task})


__all__ = ["CoderAgent", "PlannerAgent", "ReviewerAgent", "DebuggerAgent"]
