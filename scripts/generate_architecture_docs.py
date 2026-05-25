"""Generate source-backed architecture documentation facts.

This tool intentionally parses Python source with `ast` instead of importing
modules. Some project modules talk to the filesystem, environment, or GUI
libraries at import/runtime boundaries; architecture docs should not trigger
those side effects just to build a dependency map.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Symbol:
    """Public module-level class or function."""

    kind: str
    name: str
    line: int
    summary: str


@dataclass
class ModuleFacts:
    """Source facts extracted from one Python module."""

    module: str
    path: Path
    summary: str
    imports: set[str] = field(default_factory=set)
    symbols: list[Symbol] = field(default_factory=list)


@dataclass(frozen=True)
class TestFacts:
    """Relationship between a test file and the source modules it names."""

    path: Path
    imports: tuple[str, ...]
    inferred_modules: tuple[str, ...]


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    module_prefix = args.module_prefix.rstrip(".")
    source_root = args.source.resolve()
    output_dir = args.output.resolve()
    tests_root = args.tests.resolve() if args.tests else None

    modules = _collect_modules(source_root, module_prefix)
    module_names = set(modules)
    for facts in modules.values():
        facts.imports = _first_party_imports(facts.path, facts.module, module_names)

    test_facts = _collect_tests(tests_root, module_prefix, module_names) if tests_root else []

    output_dir.mkdir(parents=True, exist_ok=True)
    command = _command_string(args)
    scope = f"source={_rel(source_root)}"
    if tests_root:
        scope += f", tests={_rel(tests_root)}"

    (output_dir / f"{args.name}-imports.mmd").write_text(
        _render_import_graph(modules, command, scope, module_prefix),
        encoding="utf-8",
    )
    (output_dir / f"{args.name}-symbols.md").write_text(
        _render_symbols(modules, command, scope),
        encoding="utf-8",
    )
    if tests_root:
        (output_dir / f"{args.name}-test-map.md").write_text(
            _render_test_map(modules, test_facts, command, scope),
            encoding="utf-8",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Python source root to scan.")
    parser.add_argument("--tests", type=Path, help="Optional test root to scan.")
    parser.add_argument("--output", type=Path, required=True, help="Directory for generated docs.")
    parser.add_argument(
        "--module-prefix",
        required=True,
        help="Dotted module prefix matching --source, e.g. automations.ln_voice_over.",
    )
    parser.add_argument(
        "--name",
        default="lnvo",
        help="Output filename prefix. Defaults to 'lnvo'.",
    )
    return parser.parse_args()


def _collect_modules(source_root: Path, module_prefix: str) -> dict[str, ModuleFacts]:
    modules: dict[str, ModuleFacts] = {}
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = _module_name(path, source_root, module_prefix)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules[module] = ModuleFacts(
            module=module,
            path=path,
            summary=_first_sentence(ast.get_docstring(tree) or ""),
            symbols=_public_symbols(tree),
        )
    return modules


def _module_name(path: Path, source_root: Path, module_prefix: str) -> str:
    rel = path.relative_to(source_root).with_suffix("")
    parts = list(rel.parts)
    if parts == ["__init__"]:
        return module_prefix
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([module_prefix, *parts]) if parts else module_prefix


def _public_symbols(tree: ast.Module) -> list[Symbol]:
    symbols: list[Symbol] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith("_"):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        symbols.append(
            Symbol(
                kind=kind,
                name=node.name,
                line=node.lineno,
                summary=_first_sentence(ast.get_docstring(node) or ""),
            )
        )
    return symbols


def _first_party_imports(path: Path, module: str, module_names: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _known_target(alias.name, module_names)
                if target and target != module:
                    imports.add(target)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from(node, module)
            if not base:
                continue
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                target = _known_target(candidate, module_names) or _exact_target(
                    base, module_names
                )
                if target and target != module:
                    imports.add(target)
    return imports


def _resolve_import_from(node: ast.ImportFrom, module: str) -> str | None:
    if node.level == 0:
        return node.module

    module_parts = module.split(".")
    parent_parts = module_parts[: -node.level]
    if not parent_parts:
        return node.module
    if node.module:
        return ".".join([*parent_parts, node.module])
    return ".".join(parent_parts)


def _known_target(imported: str | None, module_names: set[str]) -> str | None:
    if not imported:
        return None
    parts = imported.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in module_names:
            return candidate
        parts.pop()
    return None


def _exact_target(imported: str | None, module_names: set[str]) -> str | None:
    if imported and imported in module_names:
        return imported
    return None


def _collect_tests(
    tests_root: Path,
    module_prefix: str,
    module_names: set[str],
) -> list[TestFacts]:
    facts: list[TestFacts] = []
    for path in sorted(tests_root.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = sorted(_test_imports(tree, module_prefix, module_names))
        inferred = sorted(_inferred_modules_from_test_name(path, module_names))
        facts.append(
            TestFacts(
                path=path,
                imports=tuple(imports),
                inferred_modules=tuple(inferred),
            )
        )
    return facts


def _test_imports(tree: ast.Module, module_prefix: str, module_names: set[str]) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(module_prefix):
                    target = _known_target(alias.name, module_names)
                    if target:
                        imports.add(target)
        elif isinstance(node, ast.ImportFrom):
            if not node.module or not node.module.startswith(module_prefix):
                continue
            alias_targets = {
                target
                for alias in node.names
                if (target := _known_target(f"{node.module}.{alias.name}", module_names))
            }
            if alias_targets:
                imports.update(alias_targets)
                continue
            if base_target := _exact_target(node.module, module_names):
                imports.add(base_target)
    return imports


def _inferred_modules_from_test_name(path: Path, module_names: set[str]) -> set[str]:
    stem = path.stem
    if not stem.startswith("test_"):
        return set()
    subject = stem.removeprefix("test_")
    # test_parse_cleaning.py primarily protects parse.py; progressively drop
    # suffixes until a module basename matches.
    parts = subject.split("_")
    candidates = ["_".join(parts[:i]) for i in range(len(parts), 0, -1)]
    basenames = {module.rsplit(".", 1)[-1]: module for module in module_names}
    return {basenames[candidate] for candidate in candidates if candidate in basenames}


def _render_import_graph(
    modules: dict[str, ModuleFacts],
    command: str,
    scope: str,
    module_prefix: str,
) -> str:
    ordered = sorted(modules)
    ids = {module: f"M{i}" for i, module in enumerate(ordered, 1)}
    lines = [
        "%% Generated by scripts/generate_architecture_docs.py",
        f"%% Command: {command}",
        f"%% Scope: {scope}",
        "flowchart LR",
    ]
    for module in ordered:
        lines.append(f'  {ids[module]}["{_short_module(module, module_prefix)}"]')
    for source in ordered:
        for target in sorted(modules[source].imports):
            lines.append(f"  {ids[source]} --> {ids[target]}")
    lines.extend(
        [
            "  classDef core fill:#eef6ff,stroke:#2563eb,color:#0f172a;",
            "  classDef script fill:#f8fafc,stroke:#64748b,color:#0f172a;",
        ]
    )
    core_ids = [ids[m] for m in ordered if ".scripts." not in m]
    script_ids = [ids[m] for m in ordered if ".scripts." in m]
    if core_ids:
        lines.append(f"  class {','.join(core_ids)} core;")
    if script_ids:
        lines.append(f"  class {','.join(script_ids)} script;")
    return "\n".join(lines) + "\n"


def _render_symbols(
    modules: dict[str, ModuleFacts],
    command: str,
    scope: str,
) -> str:
    lines = [
        "# LN Voice-Over Public Symbol Inventory",
        "",
        "> Generated by `scripts/generate_architecture_docs.py`.",
        f"> Command: `{command}`",
        f"> Scope: `{scope}`",
        "",
    ]
    for module, facts in sorted(modules.items()):
        rel_path = _rel(facts.path)
        lines.extend([f"## `{module}`", "", f"Path: `{rel_path}`", ""])
        if facts.summary:
            lines.extend([facts.summary, ""])
        if not facts.symbols:
            lines.extend(["No public module-level classes or functions detected.", ""])
            continue
        lines.extend(["| Kind | Symbol | Line | Summary |", "| --- | --- | ---: | --- |"])
        for symbol in facts.symbols:
            summary = symbol.summary or ""
            lines.append(
                f"| {symbol.kind} | `{symbol.name}` | {symbol.line} | {_escape_table(summary)} |"
            )
        lines.append("")
    return "\n".join(lines)


def _render_test_map(
    modules: dict[str, ModuleFacts],
    tests: list[TestFacts],
    command: str,
    scope: str,
) -> str:
    module_to_tests: dict[str, list[Path]] = {module: [] for module in modules}
    for test in tests:
        targets = set(test.imports) | set(test.inferred_modules)
        for module in targets:
            if module in module_to_tests:
                module_to_tests[module].append(test.path)

    lines = [
        "# LN Voice-Over Test Map",
        "",
        "> Generated by `scripts/generate_architecture_docs.py`.",
        f"> Command: `{command}`",
        f"> Scope: `{scope}`",
        "",
        "## Module Coverage Map",
        "",
        "| Module | Tests |",
        "| --- | --- |",
    ]
    for module in sorted(modules):
        tests_text = "<br>".join(
            f"`{_rel(path)}`" for path in sorted(set(module_to_tests[module]))
        )
        if not tests_text:
            tests_text = "_No direct test found_"
        lines.append(f"| `{module}` | {tests_text} |")

    lines.extend(["", "## Test File Imports", "", "| Test file | Imported source modules |"])
    lines.append("| --- | --- |")
    for test in tests:
        imports = "<br>".join(f"`{module}`" for module in test.imports)
        inferred = "<br>".join(f"`{module}`" for module in test.inferred_modules)
        details = imports or inferred or "_No direct source import or filename inference_"
        if imports and inferred and imports != inferred:
            details += f"<br>_Filename inference:_ {inferred}"
        lines.append(f"| `{_rel(test.path)}` | {details} |")
    lines.append("")
    return "\n".join(lines)


def _first_sentence(text: str) -> str:
    text = " ".join(text.strip().split())
    if not text:
        return ""
    for delimiter in (". ", "? ", "! "):
        if delimiter in text:
            return text.split(delimiter, 1)[0] + delimiter.strip()
    return text


def _short_module(module: str, module_prefix: str) -> str:
    if module == module_prefix:
        return "__init__"
    prefix = f"{module_prefix}."
    return module.removeprefix(prefix)


def _escape_table(text: str) -> str:
    return text.replace("|", "\\|")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _command_string(args: argparse.Namespace) -> str:
    parts = [
        "uv run --locked python scripts/generate_architecture_docs.py",
        f"--source {_rel(args.source)}",
    ]
    if args.tests:
        parts.append(f"--tests {_rel(args.tests)}")
    parts.extend(
        [
            f"--output {_rel(args.output)}",
            f"--module-prefix {args.module_prefix}",
            f"--name {args.name}",
        ]
    )
    return " ".join(parts)


if __name__ == "__main__":
    main()
