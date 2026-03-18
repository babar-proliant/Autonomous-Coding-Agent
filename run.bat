@echo off
start "Frontend" cmd /k "bun run dev"
start "Backend" cmd /k "cd backend && uvicorn main:app --reload --port 8000"