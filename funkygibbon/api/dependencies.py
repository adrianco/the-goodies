"""
Shared FastAPI dependencies.

ADR-003: the graph index is owned by the application (``app.state.graph_index``)
and reaches routers only through the two dependencies below. Routers must not
construct a ``GraphIndex``, and there is no module-level instance anywhere.
"""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..graph.index import GraphIndex
from ..graph.index_service import GraphIndexService


def get_graph_index_service(request: Request) -> GraphIndexService:
    """The application-owned graph index service.

    Mutating endpoints depend on this so they can write through to the index in
    the same code path as the storage write.
    """
    service = getattr(request.app.state, "graph_index", None)
    if service is None:
        raise RuntimeError(
            "No GraphIndexService on app.state -- the application was not built "
            "by funkygibbon.api.app.create_app(). See ADR-003."
        )
    return service


async def get_graph_index(
    db: AsyncSession = Depends(get_db),
    service: GraphIndexService = Depends(get_graph_index_service),
) -> GraphIndex:
    """A graph index that reflects storage.

    Loads on first use and runs the ADR-003 drift check (a cheap marker read)
    before handing the index to a reader, so a write that bypassed write-through
    costs a rebuild rather than a wrong answer.
    """
    return await service.ensure_current(db)
