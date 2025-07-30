"""Allow running as python -m funkygibbon"""
import uvicorn
from .config import settings

if __name__ == "__main__":
    # Debug: Print database URL on startup
    print(f"DEBUG: Starting server with DATABASE_URL={settings.database_url}")
    
    uvicorn.run(
        "funkygibbon.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False  # Disable reload for testing
    )