#!/usr/bin/env python3
"""
Aegis-Bio Backend CLI Entry Point
NASA Space Apps Challenge - Team Sigmoid
"""
import sys
import uvicorn
from app.config import settings

def main():
    print("=" * 65)
    print("  AEGIS-BIO :: Autonomous Clinical Flight Surgeon System")
    print("  NASA Space Apps Challenge | Artemis Lunar / Mars Transit")
    print(f"  Listening on: http://{settings.HOST}:{settings.PORT}")
    print(f"  Docs available: http://{settings.HOST}:{settings.PORT}/docs")
    print("=" * 65)
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        # Only watch the source code. Watching the whole folder includes venv/, so installing a
        # package restarts the server mid-request (seen with: pip install -r requirements.txt).
        reload_dirs=["app"],
        log_level="info",
    )

if __name__ == "__main__":
    main()
