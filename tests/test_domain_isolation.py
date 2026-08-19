"""The engine must not know about any specific domain (ADR-012).

This is the property a second domain exists to prove, and the one that decays
fastest without enforcement: reaching for `EntityType.DEVICE` in engine code is
a one-line convenience that nothing else notices. By the time a third domain
arrives it is expensive to undo.

So it is a test, not a review guideline. It fails at the moment the line is
added.

Direction matters: a domain may import the engine — that is the dependency the
design intends. Only the reverse is forbidden.
"""

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The engine. Nothing here may import a domain.
ENGINE_ROOTS = ("funkygibbon", "inbetweenies", "blowing-off")

# Test trees are excluded: a test may legitimately import a domain to exercise
# it. The rule is about what the engine *ships*, not what verifies it.
EXCLUDED_PARTS = {"tests", "build", "venv", "__pycache__", "node_modules", ".git"}


def _engine_modules():
    for root in ENGINE_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if EXCLUDED_PARTS & set(path.relative_to(REPO_ROOT).parts):
                continue
            yield path


def _imported_names(path: pathlib.Path):
    """Every module name this file imports, via either import form."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
        pytest.fail(f"could not parse {path}: {exc}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            # `level > 0` is a relative import, which cannot reach `domains`
            # from inside an engine package.
            if node.module and node.level == 0:
                yield node.module


def test_the_engine_never_imports_a_domain():
    offenders = [
        (path.relative_to(REPO_ROOT), name)
        for path in _engine_modules()
        for name in _imported_names(path)
        if name == "domains" or name.startswith("domains.")
    ]

    assert not offenders, (
        "engine code imported a domain package — the engine must take a "
        "manifest, not know a vocabulary:\n"
        + "\n".join(f"  {p}: imports {n}" for p, n in offenders)
    )


def test_the_check_can_actually_fail():
    """A guard nobody has seen fail is a guard nobody should trust.

    The scan is easy to get subtly wrong — an exclusion that swallows the whole
    tree, a walk that never yields — and it would then pass forever while
    checking nothing.
    """
    scanned = list(_engine_modules())
    assert len(scanned) > 50, (
        f"only {len(scanned)} engine modules scanned; the filter is too broad "
        "and this test is not actually looking at the engine"
    )

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        planted = pathlib.Path(tmp) / "leak.py"
        planted.write_text("from domains.house import HOUSE\n")
        assert any(
            n == "domains" or n.startswith("domains.")
            for n in _imported_names(planted)
        ), "the import scanner fails to detect a domain import it is shown"


def test_a_domain_may_import_the_engine():
    """The intended direction, pinned so nobody 'fixes' it symmetrically."""
    from domains.house import HOUSE

    assert HOUSE.name == "house"
    assert HOUSE.entity_types, "the house manifest declares a vocabulary"
