"""Allow running as python -m funkygibbon"""
import uvicorn
from .config import settings

if __name__ == "__main__":
    uvicorn.run(
        "funkygibbon.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False  # Disable reload for testing
    )