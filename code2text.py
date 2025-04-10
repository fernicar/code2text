#!/usr/bin/env python3
"""
Code to Text Converter

This script takes a Python file as input and creates a text file that contains
the content of all imported files (that are part of the project), followed by
the content of the main file.

Usage:
    python code2text.py main.py [output.txt]
"""

import ast
import os
import sys
from collections import defaultdict, deque
from pathlib import Path


class ImportAnalyzer(ast.NodeVisitor):
    """AST visitor that extracts import statements from Python code."""

    def __init__(self, base_path):
        self.imports = set()
        self.base_path = Path(base_path).parent

    def visit_Import(self, node):
        """Handle 'import module' statements."""
        for name in node.names:
            module_name = name.name
            if not self._is_stdlib_module(module_name):
                self.imports.add(module_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Handle 'from module import name' statements."""
        if node.module is None:  # Handle 'from . import name'
            return

        if node.level > 0:  # Relative import
            # Resolve relative import based on current file's location
            parts = self.base_path.parts
            if node.level > len(parts):
                print(f"Warning: Cannot resolve relative import {node.module} with level {node.level}")
                return

            # Go up node.level directories
            parent_path = self.base_path.parents[node.level - 1] if node.level > 1 else self.base_path

            if node.module:
                # Convert module name to path
                module_path = parent_path / node.module.replace('.', '/')
                self.imports.add(f".{'.' * (node.level-1)}{node.module}")
        else:
            # Absolute import
            if not self._is_stdlib_module(node.module):
                self.imports.add(node.module)

        self.generic_visit(node)

    def _is_stdlib_module(self, module_name):
        """Check if a module is part of the standard library."""
        # This is a simplified check - in a real implementation, you might want
        # to check against a list of standard library modules
        return module_name.split('.')[0] in sys.builtin_module_names


def find_project_root():
    """Find the root directory of the project."""
    # This is a simplified implementation - in a real project, you might want to
    # look for specific files like pyproject.toml, setup.py, etc.
    return os.getcwd()


def resolve_module_path(module_name, current_file_path, project_root):
    """Convert a module name to a file path."""
    if module_name.startswith('.'):
        # Relative import
        level = 0
        for char in module_name:
            if char == '.':
                level += 1
            else:
                break

        module_name = module_name[level:]
        parent_dir = Path(current_file_path).parent

        # Go up 'level' directories
        for _ in range(level - 1):
            parent_dir = parent_dir.parent

        if module_name:
            module_path = parent_dir / f"{module_name.replace('.', '/')}.py"
        else:
            module_path = parent_dir / "__init__.py"
    else:
        # Absolute import (within project)
        module_path = Path(project_root) / f"{module_name.replace('.', '/')}.py"

        # Check if it's a package (has __init__.py)
        package_path = Path(project_root) / module_name.replace('.', '/')
        if package_path.is_dir() and (package_path / "__init__.py").exists():
            module_path = package_path / "__init__.py"

    return module_path


def analyze_imports(file_path, project_root):
    """Analyze imports in a Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()

    try:
        tree = ast.parse(source)
        analyzer = ImportAnalyzer(file_path)
        analyzer.visit(tree)

        # Resolve import paths
        import_paths = []
        for module_name in analyzer.imports:
            try:
                module_path = resolve_module_path(module_name, file_path, project_root)
                if module_path.exists() and str(module_path).startswith(project_root):
                    import_paths.append(str(module_path))
            except Exception as e:
                print(f"Warning: Could not resolve import {module_name}: {e}")

        return import_paths
    except SyntaxError as e:
        print(f"Error parsing {file_path}: {e}")
        return []


def build_dependency_graph(entry_file, project_root):
    """Build a graph of file dependencies."""
    graph = defaultdict(list)
    visited = set()
    queue = deque([entry_file])

    while queue:
        file_path = queue.popleft()
        if file_path in visited:
            continue

        visited.add(file_path)
        imports = analyze_imports(file_path, project_root)

        for imported_file in imports:
            graph[file_path].append(imported_file)
            if imported_file not in visited:
                queue.append(imported_file)

    return graph


def topological_sort(graph):
    """Sort files in order of dependencies (deepest first)."""
    result = []
    visited = set()
    temp_visited = set()

    def visit(node):
        if node in temp_visited:
            # Circular dependency detected
            print(f"Warning: Circular dependency detected involving {node}")
            return
        if node in visited:
            return

        temp_visited.add(node)

        for neighbor in graph.get(node, []):
            visit(neighbor)

        temp_visited.remove(node)
        visited.add(node)
        result.append(node)

    for node in graph:
        if node not in visited:
            visit(node)

    return result


def create_combined_file(sorted_files, output_file, project_root):
    """Create a combined file with all dependencies."""
    with open(output_file, 'w', encoding='utf-8') as out:
        for file_path in sorted_files:
            # Get the relative path from the project root
            try:
                rel_path = os.path.relpath(file_path, project_root)
            except ValueError:
                # If the file is on a different drive, use the absolute path
                rel_path = file_path

            out.write(f"```\n# Start of {rel_path}\n")

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    out.write(content)
                    if not content.endswith('\n'):
                        out.write('\n')
            except Exception as e:
                out.write(f"# Error reading file: {e}\n")

            out.write(f"# End of {rel_path}\n```\n\n")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <python_file> [output_file]")
        sys.exit(1)

    input_file = os.path.abspath(sys.argv[1])
    if not os.path.exists(input_file):
        print(f"Error: File {input_file} does not exist")
        sys.exit(1)

    output_file = sys.argv[2] if len(sys.argv) > 2 else "combined_output.txt"

    project_root = find_project_root()
    print(f"Project root: {project_root}")
    print(f"Analyzing imports for {input_file}...")

    # Build dependency graph
    graph = build_dependency_graph(input_file, project_root)

    # Sort files by dependency order
    sorted_files = topological_sort(graph)

    # The entry file should be last
    if input_file in sorted_files:
        sorted_files.remove(input_file)
    sorted_files.append(input_file)

    print(f"Found {len(sorted_files) - 1} dependencies")

    # Create combined file
    create_combined_file(sorted_files, output_file, project_root)
    print(f"Combined file created: {output_file}")


if __name__ == "__main__":
    main()
