@echo off
rem Starts PharmaCompare: backend (Flask, port 5000) and frontend (Vite, port 5173).
rem MySQL must already be running (it is a Windows service).
rem The backend takes about 20-30 seconds to load the OCR libraries; wait for
rem its window to print "Running on http://127.0.0.1:5000" before uploading.

start "PharmaCompare backend" cmd /k "cd /d D:\PharmaCompare\backend && venv\Scripts\python.exe run.py"
start "PharmaCompare frontend" cmd /k "cd /d D:\PharmaCompare\frontend && npm run dev"

timeout /t 6 /nobreak >nul
start "" http://localhost:5173
