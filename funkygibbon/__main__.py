"""Allow running as python -m funkygibbon"""
from .main import app
import uvicorn
from .config import settings

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )