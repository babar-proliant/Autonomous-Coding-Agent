# 🤖 Autonomous Coding Agent

<div align="center">

![Next.js](https://img.shields.io/badge/Next.js-16.1.1-black?style=flat-square&logo=next.js)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi)
![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=flat-square&logo=typescript)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

**AI-Powered Software Development Assistant with Local LLMs**

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Documentation](#-documentation)

</div>

---

## 📖 Overview

Autonomous Coding Agent is a full-stack AI-powered software development assistant that can autonomously plan, write, test, and debug code. Describe what you want to build, and watch as the AI agent creates it from scratch with real-time streaming output.

<img width="1919" height="923" alt="Screenshot 2026-03-19 013211" src="https://github.com/user-attachments/assets/5b1f129f-a300-40f9-b8a6-b14a90d2be56" />


### Why This Project?

- 🔒 **100% Local** - No data leaves your machine. Runs entirely on local LLMs.
- 🚀 **Real-Time Streaming** - See the AI's thought process and code generation as it happens.
- 🛠️ **Multi-Agent System** - Specialized agents for planning, coding, reviewing, and debugging.
- 💻 **Full-Stack** - Modern React frontend with Python FastAPI backend.
- 🔧 **Tool Integration** - Safe file operations and terminal command execution.

---

## ✨ Features

### 🤖 AI Agent Capabilities

| Feature | Description |
|---------|-------------|
| **Autonomous Code Generation** | Write complete files from natural language descriptions |
| **Multi-Agent Collaboration** | Specialized agents handle planning, coding, review, and debugging |
| **Iterative Refinement** | Agents execute multiple iterations, learning from tool results |
| **Context Awareness** | Working memory maintains conversation history |

### 📝 Code Generation

- **Natural Language to Code** - Describe what you want, the agent writes the code
- **AST-Based Tool Calling** - LLM outputs Python function calls that are parsed and executed
- **Multiple File Formats** - Supports Python, JavaScript/TypeScript, HTML, CSS, and more
- **Multi-File Projects** - Create entire projects with multiple interconnected files

### 📁 File Management

- **Read Files** - View any file in the workspace with syntax highlighting
- **Write Files** - Create new files with complete content
- **Edit Files** - Replace specific text in existing files
- **Directory Operations** - List, create, search directories
- **Upload/Download** - Upload files/folders, download individual files or project as ZIP

### ⚡ Real-Time Streaming

- **Token-by-Token Output** - See the AI's response as it generates
- **Live Activity Feed** - Real-time view of agent actions and tool executions
- **SSE Events** - Robust event streaming with heartbeat and reconnection

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
├─────────────────┬───────────────────┬───────────────────────────┤
│   Chat Panel    │   Workspace Panel │      Header / Footer      │
│   (React)       │   (Monaco Editor) │      (Status Badges)      │
└────────┬────────┴─────────┬─────────┴───────────────────────────┘
         │                  │
         │ SSE Events       │ REST API
         ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
├─────────────────┬───────────────────┬───────────────────────────┤
│   Event Bus     │   API Routes      │      Session Manager      │
│   (SSE Stream)  │   (REST)          │      (State)              │
└────────┬────────┴─────────┬─────────┴───────────────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent System                                │
├─────────────────┬───────────────────┬───────────────────────────┤
│  Orchestrator   │   Specialist      │      Tool Registry        │
│  (Router)       │   Agents          │      (Execution)          │
└────────┬────────┴─────────┬─────────┴───────────────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Local LLM (llama-cpp)                         │
│                    Qwen 2.5 Coder 14B                            │
└─────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
autonomous-coding-agent/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Application entry point
│   ├── config.py           # Settings and configuration
│   ├── api/
│   │   └── routes.py       # API endpoints
│   ├── agents/
│   │   ├── base_agent.py   # Abstract base agent
│   │   ├── orchestrator.py # Chief orchestrator
│   │   └── coder_agent.py  # Specialist agents
│   ├── models/
│   │   └── model_manager.py # LLM management
│   ├── tools/
│   │   ├── base_tool.py    # Tool framework
│   │   ├── code_parser.py  # AST parser
│   │   └── filesystem/     # File operations
│   ├── core/
│   │   └── event_bus.py    # SSE streaming
│   └── memory/
│       └── working_memory.py # Context management
├── src/                     # Next.js frontend
│   ├── app/
│   │   ├── page.tsx        # Main application
│   │   ├── layout.tsx      # Root layout
│   │   └── api/            # API routes
│   ├── components/
│   │   ├── chat/           # Chat interface
│   │   ├── workspace/      # File browser & editor
│   │   └── ui/             # shadcn/ui components
│   ├── hooks/
│   │   ├── useSSE.ts       # SSE management
│   │   └── useAgent.ts     # Agent API
│   └── stores/
│       └── chatStore.ts    # Zustand state
├── prisma/                  # Database schema
├── workspaces/              # Generated projects
└── models/                  # LLM model files
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **Node.js 18+** or **Bun**
- **CUDA-capable GPU** (recommended) or CPU
- **~10GB disk space** for model

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/autonomous-coding-agent.git
cd autonomous-coding-agent
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the backend server
cd backend
python main.py
```

The backend will start at `http://localhost:8000`

### 3. Frontend Setup

```bash
# Install dependencies
bun install
# or: npm install

# Run development server
bun run dev
# or: npm run dev
```

The frontend will start at `http://localhost:3000`

### 4. Model Setup

On first run, the model will automatically download from HuggingFace:
- **Model**: Qwen 2.5 Coder 14B Instruct (Q4_K_M GGUF)
- **Size**: ~9 GB
- **Source**: [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct-GGUF)

Or manually place GGUF files in the `./models/` directory.

---

## 📚 Documentation

### Agent System

| Agent | Role | Description |
|-------|------|-------------|
| **ChiefOrchestrator** | Controller | Routes tasks to specialist agents based on intent |
| **CoderAgent** | Developer | Primary code writer with iterative generation |
| **PlannerAgent** | Architect | Creates implementation plans for complex tasks |
| **ReviewerAgent** | QA | Code quality review and improvement suggestions |
| **DebuggerAgent** | Troubleshooter | Bug diagnosis and fixing |

### Available Tools

#### Filesystem Tools

| Tool | Description | Risk Level |
|------|-------------|------------|
| `read_file` | Read file contents | 🟢 Low |
| `write_file` | Create or overwrite files | 🟡 Medium |
| `edit_file` | Replace text in files | 🟡 Medium |
| `delete_file` | Remove files | 🔴 High |
| `list_directory` | List directory contents | 🟢 Low |
| `create_directory` | Create directories | 🟢 Low |
| `find_file` | Find files by pattern | 🟢 Low |
| `search_files` | Search file contents | 🟢 Low |

#### Terminal Tools

| Tool | Description | Risk Level |
|------|-------------|------------|
| `execute_command` | Run shell commands | 🔴 High |
| `start_process` | Start background process | 🔴 High |
| `read_process_output` | Read process output | 🟢 Low |
| `stop_process` | Stop running process | 🟡 Medium |

### API Endpoints

#### Session Management
```
POST   /api/session/create     # Create new session
GET    /api/session/{id}       # Get session info
DELETE /api/session/{id}       # End session
```

#### Chat & Streaming
```
POST   /api/chat               # Send message to agent
GET    /api/events/{id}        # SSE event stream
```

#### Workspace
```
GET    /api/workspace/{id}     # List workspace files
GET    /api/file/{id}          # Read file content
POST   /api/upload/{id}        # Upload files
```

#### System
```
GET    /health                 # Health check
GET    /api/status             # System status
GET    /api/models/status      # Model status
```

### SSE Event Types

| Event | Description |
|-------|-------------|
| `connected` | SSE connection established |
| `thinking_start` | Agent begins processing |
| `thinking_stream` | Token-by-token output |
| `thinking_end` | Agent finished thinking |
| `tool_start` | Tool execution begins |
| `tool_result` | Tool execution result |
| `agent_switch` | Switched to different agent |
| `done` | Task completed |
| `error` | Error occurred |

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
DATABASE_URL=file:./db/custom.db
```

### Backend Settings (`backend/config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `model_name` | `qwen2.5-coder-14b-instruct-q4_k_m.gguf` | Model filename |
| `model_temperature` | `0.7` | Generation temperature |
| `model_max_tokens` | `2048` | Max output tokens |
| `model_context_window` | `8192` | Context window size |
| `gpu_layers` | `45` | GPU layers for acceleration |
| `max_tool_execution_time` | `300` | Tool timeout (seconds) |
| `auto_download_models` | `True` | Auto-download from HuggingFace |

### Frontend Settings

The frontend uses Next.js with Tailwind CSS. Key configuration files:
- `next.config.ts` - Next.js configuration
- `tailwind.config.ts` - Tailwind CSS configuration
- `src/lib/utils.ts` - Utility functions

---

## 🎯 Usage Examples

### Creating a Website

```
User: Create a landing page for a pizza restaurant with a menu section,
contact form, and about us page. Use modern CSS with animations.

Agent: I'll create a multi-page pizza restaurant website. Let me start
by planning the structure and then implementing each file...

[Creates index.html, menu.html, contact.html, about.html, styles.css]
```

### Building a CLI Tool

```
User: Create a Python CLI tool that can resize images in bulk,
supporting JPEG, PNG, and WebP formats with quality settings.

Agent: I'll create a Python CLI tool for bulk image resizing using
Pillow library...

[Creates image_resizer.py with argparse CLI, README.md]
```

### Debugging Code

```
User: The login function in auth.py is not working. When I submit
the form, it shows "Invalid credentials" even with correct passwords.

Agent: Let me analyze the authentication code to identify the issue...

[Reads auth.py, identifies bcrypt hash comparison bug, fixes it]
```

---

## 🖥️ Screenshots

### Main Interface
![Main Interface](./screenshots/main-interface.png)

### Code Generation in Progress
![Code Generation](./screenshots/code-generation.png)

### File Preview
![File Preview](./screenshots/file-preview.png)

---

## 🛠️ Tech Stack

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 16.1.1 | React framework with App Router |
| React | 19.0.0 | UI library |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 4.x | Styling |
| shadcn/ui | Latest | UI components |
| Zustand | 5.0.6 | State management |
| Monaco Editor | Latest | Code editor |
| react-markdown | 10.1.0 | Markdown rendering |

### Backend
| Technology | Purpose |
|------------|---------|
| Python 3.12+ | Runtime |
| FastAPI | Web framework |
| Uvicorn | ASGI server |
| llama-cpp-python | Local LLM inference |
| aiofiles | Async file operations |
| psutil | System monitoring |

### AI Model
| Model | Details |
|-------|---------|
| Qwen 2.5 Coder 14B Instruct | Primary coding model |
| Quantization | Q4_K_M (~9GB VRAM) |
| Context Window | 8192 tokens |
| GPU Acceleration | CUDA (45 layers) |

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Qwen Team](https://github.com/QwenLM/Qwen) for the excellent coding model
- [llama.cpp](https://github.com/ggerganov/llama.cpp) for efficient LLM inference
- [shadcn/ui](https://ui.shadcn.com/) for beautiful UI components
- [FastAPI](https://fastapi.tiangolo.com/) for the amazing backend framework

---

<div align="center">

**Made with ❤️ by the Autonomous Coding Agent Team**

[⬆ Back to Top](#-autonomous-coding-agent)

</div>
