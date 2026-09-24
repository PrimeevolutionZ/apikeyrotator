#!/usr/bin/env python
"""
Checks the Markdown documentation against the real library.

For every ```python block (blocks fenced as ```python signature are skipped):
- the code parses;
- names imported from apikeyrotator exist;
- keyword arguments passed to apikeyrotator classes/functions exist in their signatures;
- methods/attributes used on objects created from apikeyrotator classes exist.

For every Markdown file:
- relative links point to existing files;
- #anchors point to existing headings (GitHub-style slugs).

Usage:
    python scripts/check_docs.py            # all docs
    python scripts/check_docs.py README.md  # selected files

Exit code 1 if problems were found.
"""

from __future__ import annotations
import ast
import glob
import importlib
import inspect
import os
import re
import sys
import textwrap


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import apikeyrotator  # noqa: E402


DEFAULT_FILES = [
    "README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md",
    *sorted(glob.glob("docs/*.md", root_dir=ROOT)), "benchmarks/README.md", "benchmarks/RESULTS.md",
]
CODE_BLOCK = re.compile(r"^(```|~~~)python[ \t]*\n(.*?)^\1[ \t]*$", re.S | re.M)
FENCE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.S | re.M)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)


# ----------------------------------------------------------------------------
# Code checks
# ----------------------------------------------------------------------------

def _resolve(module: str, name: str):
    try:
        mod = importlib.import_module(module)
    except Exception as e:
        return None, f"module {module!r} is not importable ({type(e).__name__})"
    if hasattr(mod, name):
        return getattr(mod, name), None
    try:
        return importlib.import_module(f"{module}.{name}"), None
    except Exception:
        return None, f"{module} has no {name!r}"


def _accepts(obj, keyword: str) -> bool:
    target = obj.__init__ if inspect.isclass(obj) else obj
    try:
        params = inspect.signature(target).parameters
    except (TypeError, ValueError):
        return True
    if keyword in params:
        return True
    if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return False
    # **kwargs forwarded to a base class (e.g. APIKeyRotator -> BaseKeyRotator)
    if inspect.isclass(obj):
        for base in obj.__mro__[1:]:
            if "__init__" in base.__dict__ and base.__module__.startswith("apikeyrotator"):
                base_params = inspect.signature(base.__init__).parameters
                if keyword in base_params:
                    return True
                if not any(p.kind == p.VAR_KEYWORD for p in base_params.values()):
                    return False
    return True


def _has_attribute(cls, attr: str) -> bool:
    if hasattr(cls, attr):
        return True
    # instance attributes assigned in __init__ of the class or its apikeyrotator bases
    for klass in cls.__mro__:
        if not klass.__module__.startswith("apikeyrotator"):
            continue
        try:
            source = inspect.getsource(klass)
        except (OSError, TypeError):
            continue
        if re.search(rf"self\.{re.escape(attr)}\b\s*[:=]", source):
            return True
    return False


def check_code(code: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [(e.lineno or 1, f"SyntaxError: {e.msg}")]

    problems: list[tuple[int, str]] = []
    # Docs often omit imports of public names - treat them as available
    names = {n: getattr(apikeyrotator, n) for n in apikeyrotator.__all__}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("apikeyrotator"):
            for alias in node.names:
                obj, err = _resolve(node.module, alias.name)
                if err:
                    problems.append((node.lineno, f"import: {err}"))
                else:
                    names[alias.asname or alias.name] = obj

    instances: dict[str, type] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and isinstance(node.value.func, ast.Name):
            cls = names.get(node.value.func.id)
            if inspect.isclass(cls):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        instances[target.id] = cls
                    elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
                            and target.value.id == "self":
                        instances["self." + target.attr] = cls
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) \
                        and isinstance(item.optional_vars, ast.Name):
                    cls = names.get(expr.func.id)
                    if inspect.isclass(cls):
                        instances[item.optional_vars.id] = cls

    def owner_key(node) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            return "self." + node.attr
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            key = owner_key(node.value)
            if key in instances and not _has_attribute(instances[key], node.attr):
                problems.append((node.lineno, f"{instances[key].__name__} has no attribute {node.attr!r}"))

        if not isinstance(node, ast.Call):
            continue
        func, target = node.func, None
        if isinstance(func, ast.Name) and func.id in names:
            target = names[func.id]
        elif isinstance(func, ast.Attribute):
            key = owner_key(func.value)
            if key in instances and hasattr(instances[key], func.attr):
                target = getattr(instances[key], func.attr)
            elif isinstance(func.value, ast.Name) and inspect.ismodule(names.get(func.value.id)):
                module = names[func.value.id]
                if not hasattr(module, func.attr):
                    problems.append((node.lineno, f"{module.__name__} has no {func.attr!r}"))
                    continue
                target = getattr(module, func.attr)
            elif isinstance(func.value, ast.Name) and inspect.isclass(names.get(func.value.id)):
                cls = names[func.value.id]
                if not hasattr(cls, func.attr):
                    problems.append((node.lineno, f"{cls.__name__} has no attribute {func.attr!r}"))
                    continue
                target = getattr(cls, func.attr)
        if target is None or not callable(target):
            continue
        for keyword in node.keywords:
            if keyword.arg and not _accepts(target, keyword.arg):
                name = getattr(target, "__qualname__", repr(target))
                problems.append((node.lineno, f"{name}() has no parameter {keyword.arg!r}"))
    return problems


# ----------------------------------------------------------------------------
# Link checks
# ----------------------------------------------------------------------------

def slugify(heading: str) -> str:
    """GitHub-style anchor for a heading."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)            # inline code
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)    # links
    text = text.strip().lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_")
    return text.replace(" ", "-")


def anchors_of(path: str) -> set[str]:
    with open(path, encoding="utf-8") as f:
        text = FENCE.sub("", f.read())
    seen: dict[str, int] = {}
    anchors = set()
    for match in HEADING.finditer(text):
        slug = slugify(match.group(1))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def check_links(path: str, text: str) -> list[tuple[int, str]]:
    problems = []
    base = os.path.dirname(path)
    body = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for match in LINK.finditer(body):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        line = body[:match.start()].count("\n") + 1
        file_part, _, anchor = target.partition("#")
        target_path = os.path.normpath(os.path.join(base, file_part)) if file_part else path
        if not os.path.exists(target_path):
            problems.append((line, f"broken link: {target}"))
            continue
        if anchor and target_path.endswith(".md") and anchor not in anchors_of(target_path):
            problems.append((line, f"missing anchor: {target}"))
    return problems


# ----------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    files = argv or DEFAULT_FILES
    total = 0
    for rel in files:
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        problems = check_links(path, text)
        for match in CODE_BLOCK.finditer(text):
            start_line = text[:match.start()].count("\n") + 2
            code = textwrap.dedent(match.group(2))
            problems += [(start_line + line - 1, msg) for line, msg in check_code(code)]
        for line, msg in sorted(set(problems)):
            print(f"{rel}:{line}: {msg}")
        total += len(set(problems))
    print(f"{total} problem(s) in {len(files)} file(s)", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
