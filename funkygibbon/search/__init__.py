"""
Search module for FunkyGibbon
"""

from .fts import ensure_fts_schema, register_fts_ddl

# ADR-006 §1: registering here means importing funkygibbon.search is enough to
# make create_all build the FTS index, so tests and scripts that never call
# init_db still get a searchable database.
register_fts_ddl()

__all__ = ['ensure_fts_schema', 'register_fts_ddl']
