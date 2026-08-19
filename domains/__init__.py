"""Domain packages (ADR-012).

A domain supplies vocabulary; the engine supplies everything else. Nothing in
`funkygibbon`, `inbetweenies` or `blowing-off` may import a specific domain —
they take a manifest.
"""
