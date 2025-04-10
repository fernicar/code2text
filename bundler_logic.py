import ast
import os
import sys
from pathlib import Path
from collections import deque, defaultdict
import importlib.util
from typing import Dict, List, Set, Tuple, Optional, Callable

# --- Project Root Detection ---

def find_project_root(start_path: Path) -> Optional[Path]:
    """
    Attempts to find the project root directory starting from 'start_path'
    by looking for common markers or traversing up.
    """
    current_dir = start_path.resolve()
    if current_dir.is_file():
        current_dir = current_dir.parent

    # Look for common project markers
    markers = ['.git', 'pyproject.toml', 'setup.py', 'requirements.txt', '.project_root'] # Added .project_root marker

    while True:
        for marker in markers:
            if (current_dir / marker).exists():
                return current_dir

        # Stop if we reach the filesystem root
        if current_dir.parent == current_dir:
            # Fallback: return the directory of the start_path file if no marker found
            if start_path.is_file():
                 return start_path.parent
            else:
                 return start_path # Should ideally not happen with file input
            # return None # Or return None if a marker is strictly required

        current_dir = current_dir.parent

# --- Import Analysis ---

class ImportAnalyzer(ast.NodeVisitor):
    """
    Parses a Python file's AST to find local module imports.
    """
    def __init__(self, file_path: Path, project_root: Path,
                 progress_callback: Optional[Callable[[str], None]] = None):
        self.file_path = file_path
        self.project_root = project_root
        self.local_dependencies: Set[Path] = set()
        self.log = progress_callback if progress_callback else lambda _: None
        self.log(f"  Analyzing imports in: {file_path.relative_to(project_root)}")

    def _resolve_module(self, module_name: str, level: int) -> Optional[Path]:
        """
        Tries to resolve an imported module name to a file path within the project.
        Handles relative imports based on 'level'.
        Returns the absolute path if it's a local project file, None otherwise.
        """
        # 1. Try standard/site package resolution first
        try:
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin:
                # Check if it's built-in or frozen
                if spec.origin == 'built-in' or spec.origin == 'frozen':
                     self.log(f"    -> Ignoring built-in/frozen module: {module_name}")
                     return None
                 # Check if it's outside the project root (site-package)
                origin_path = Path(spec.origin).resolve()
                if not origin_path.is_relative_to(self.project_root):
                     self.log(f"    -> Ignoring site-package/external module: {module_name}")
                     return None
                # If it's inside the project root, it *might* be local, continue resolving manually
                # This helps catch cases where a local module shadows a site-package one.
        except ModuleNotFoundError:
            pass # Module not found by standard means, likely local or error
        except Exception as e:
             self.log(f"    -> Warning: Error checking spec for {module_name}: {e}")
             # Proceed with manual resolution attempt

        # 2. Manual resolution within the project for relative and absolute imports
        base_dir = self.file_path.parent
        if level > 0: # Relative import
            # Adjust base_dir based on level (e.g., level 1 is '.', level 2 is '..')
            for _ in range(level - 1):
                base_dir = base_dir.parent

        parts = module_name.split('.')
        current_path = base_dir if level > 0 else self.project_root

        # Resolve path segments for absolute imports relative to project root
        # For relative imports, parts are resolved relative to adjusted base_dir
        if level == 0 and module_name:
             current_path = self.project_root
             path_to_try = current_path / Path(*parts)
        elif level > 0 and module_name:
            current_path = base_dir
            path_to_try = current_path / Path(*parts)
        elif level > 0 and not module_name: # from . import x -> module_name is empty
            path_to_try = current_path # Stay in the adjusted base_dir
        else: # Absolute import potentially (level 0, but could still be local)
             path_to_try = self.project_root / Path(*parts)


        # Try resolving as package (directory/__init__.py) or module (.py file)
        possible_module_path = path_to_try.with_suffix('.py')
        possible_package_path = path_to_try / '__init__.py'

        final_path = None
        if possible_module_path.is_file() and possible_module_path.is_relative_to(self.project_root):
             final_path = possible_module_path.resolve()
             self.log(f"    -> Resolved local module: {module_name} -> {final_path.relative_to(self.project_root)}")
        elif possible_package_path.is_file() and possible_package_path.is_relative_to(self.project_root):
             final_path = possible_package_path.resolve()
             self.log(f"    -> Resolved local package: {module_name} -> {final_path.relative_to(self.project_root)}")
        else:
            # Check again specifically relative to project root if not found yet (handles some edge cases)
            abs_path_try = self.project_root / Path(*parts)
            possible_module_path = abs_path_try.with_suffix('.py')
            possible_package_path = abs_path_try / '__init__.py'
            if possible_module_path.is_file() and possible_module_path.is_relative_to(self.project_root):
                 final_path = possible_module_path.resolve()
                 self.log(f"    -> Resolved local module (abs root): {module_name} -> {final_path.relative_to(self.project_root)}")
            elif possible_package_path.is_file() and possible_package_path.is_relative_to(self.project_root):
                 final_path = possible_package_path.resolve()
                 self.log(f"    -> Resolved local package (abs root): {module_name} -> {final_path.relative_to(self.project_root)}")
            else:
                self.log(f"    -> Could not resolve local path for: {module_name} (level {level}) relative to {self.file_path.name}")
                return None # Not found within the project

        return final_path


    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            resolved_path = self._resolve_module(alias.name, level=0)
            if resolved_path:
                self.local_dependencies.add(resolved_path)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        # Level > 0 indicates relative import (e.g., from . import foo -> level=1)
        resolved_path = self._resolve_module(node.module if node.module else '', level=node.level)
        if resolved_path:
            # We depend on the __init__.py or the .py file itself
            self.local_dependencies.add(resolved_path)
        elif node.module: # Log if module itself wasn't resolved, but it's not relative level 0
             self.log(f"    -> Note: Base module '{node.module}' (level {node.level}) not resolved as local project file.")

        self.generic_visit(node)

    @staticmethod
    def find_imports(file_path: Path, project_root: Path, progress_callback: Optional[Callable[[str], None]] = None) -> Set[Path]:
        """Parses a file and returns a set of absolute paths to local dependencies."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
            analyzer = ImportAnalyzer(file_path, project_root, progress_callback)
            analyzer.visit(tree)
            return analyzer.local_dependencies
        except FileNotFoundError:
            if progress_callback: progress_callback(f"  Error: File not found during import analysis: {file_path}")
            return set()
        except SyntaxError as e:
            if progress_callback: progress_callback(f"  Error: Syntax error in {file_path}: {e}")
            return set() # Continue if possible, but log error
        except Exception as e:
            if progress_callback: progress_callback(f"  Error: Unexpected error analyzing {file_path}: {e}")
            return set()

# --- Dependency Graph and Topological Sort ---

def build_dependency_graph(main_file_path: Path, project_root: Path,
                            progress_callback: Optional[Callable[[str], None]] = None) \
                            -> Tuple[Dict[Path, Set[Path]], List[Path]]:
    """
    Builds a dependency graph for the project starting from the main file.
    Returns the graph (file -> dependencies) and a list of all discovered project files.
    """
    log = progress_callback if progress_callback else lambda _: None
    log("Building dependency graph...")
    graph: Dict[Path, Set[Path]] = defaultdict(set)
    all_files: Set[Path] = set()
    queue: deque[Path] = deque([main_file_path.resolve()])
    visited: Set[Path] = set()

    while queue:
        current_file = queue.popleft()
        if current_file in visited:
            continue
        if not current_file.is_relative_to(project_root):
             log(f"  Skipping file outside project root: {current_file}")
             continue

        visited.add(current_file)
        all_files.add(current_file)

        dependencies = ImportAnalyzer.find_imports(current_file, project_root, log)
        graph[current_file] = dependencies

        for dep in dependencies:
            if dep not in visited:
                queue.append(dep)

    log("Dependency graph built.")
    return dict(graph), list(all_files)


def topological_sort(graph: Dict[Path, Set[Path]]) -> Tuple[List[Path], List[Tuple[Path, Path]]]:
    """
    Performs a topological sort on the dependency graph using DFS.
    Returns the sorted list of files and a list of detected cycles (edges).
    Uses the same algorithm as the CLI version for consistency.
    """
    result: List[Path] = []
    visited: Set[Path] = set()
    temp_visited: Set[Path] = set()
    edges_in_cycles: List[Tuple[Path, Path]] = []

    def visit(node: Path):
        if node in temp_visited:
            # Circular dependency detected
            # Record the cycle edge from the last node in temp_visited to this node
            for temp_node in temp_visited:
                if node in graph.get(temp_node, set()):
                    edges_in_cycles.append((temp_node, node))
            return
        if node in visited:
            return

        temp_visited.add(node)

        for neighbor in graph.get(node, set()):
            visit(neighbor)

        temp_visited.remove(node)
        visited.add(node)
        result.append(node)

    for node in graph:
        if node not in visited:
            visit(node)

    return result, edges_in_cycles


# --- File Combination ---

def create_combined_file(sorted_files: List[Path], output_path: Path, project_root: Path,
                          progress_callback: Optional[Callable[[str], None]] = None) -> None:
    """
    Combines the content of sorted files into a single output file.
    """
    log = progress_callback if progress_callback else lambda _: None
    log(f"Writing combined file to: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

    try:
        with open(output_path, 'w', encoding='utf-8') as outfile:
            for file_path in sorted_files:
                try:
                    relative_path_str = str(file_path.relative_to(project_root)).replace('\\', '/') # Normalize path sep
                    log(f"  Adding file: {relative_path_str}")
                    outfile.write(f"```\n# Start of {relative_path_str}\n")
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
                    outfile.write(f"# End of {relative_path_str}\n```\n\n")
                except FileNotFoundError:
                    log(f"  Error: File not found while combining: {file_path}")
                    outfile.write(f"```\n# Error: File not found: {relative_path_str}\n```\n\n")
                except Exception as e:
                    log(f"  Error: Failed to read file {file_path}: {e}")
                    outfile.write(f"```\n# Error reading file: {relative_path_str} ({e})\n```\n\n")
        log("Combined file created successfully.")
    except IOError as e:
        log(f"Error: Failed to write output file {output_path}: {e}")
        raise # Re-raise IO error for the GUI to handle
    except Exception as e:
        log(f"Error: An unexpected error occurred during file writing: {e}")
        raise # Re-raise for the GUI


# --- Orchestration ---

def run_bundling_process(main_py_file: str, output_txt_file: str,
                         progress_callback: Callable[[str], None]) -> bool:
    """
    Main function to orchestrate the bundling process.
    Returns True on success, False on failure.
    """
    progress_callback("Starting bundling process...")
    main_path = Path(main_py_file).resolve()
    output_path = Path(output_txt_file).resolve()

    if not main_path.is_file():
        progress_callback(f"Error: Main Python file not found: {main_py_file}")
        return False

    # 1. Find Project Root
    project_root = find_project_root(main_path)
    if not project_root:
        progress_callback("Error: Could not determine project root.")
        # Defaulting to main file's parent directory
        project_root = main_path.parent
        progress_callback(f"Warning: Defaulting project root to: {project_root}")
        # return False # Decide if this is a fatal error or warning
    else:
        progress_callback(f"Detected project root: {project_root}")


    # 2. Build Dependency Graph
    try:
        graph, all_files = build_dependency_graph(main_path, project_root, progress_callback)
        progress_callback("\nIdentified Project Files:")
        for f in all_files:
            progress_callback(f"- {f.relative_to(project_root)}")
        progress_callback("") # Newline
    except Exception as e:
        progress_callback(f"Error building dependency graph: {e}")
        import traceback
        progress_callback(traceback.format_exc())
        return False

    # 3. Topological Sort
    try:
        sorted_files, cycles = topological_sort(graph)
        progress_callback("Topological sort complete.")
        if cycles:
            progress_callback("\nWarning: Circular dependencies detected involving:")
            unique_cycle_nodes = set(p for edge in cycles for p in edge)
            for node in unique_cycle_nodes:
                 progress_callback(f"- {node.relative_to(project_root)}")
            progress_callback("(Bundling will proceed with a best-effort order)\n")
        else:
            progress_callback("No circular dependencies detected.\n")

        # Ensure the main file is last, just like in the CLI version
        if main_path in sorted_files:
            sorted_files.remove(main_path)
        sorted_files.append(main_path)

        progress_callback("File order for bundling:")
        for f in sorted_files:
             progress_callback(f"- {f.relative_to(project_root)}")
        progress_callback("") # Newline

    except Exception as e:
        progress_callback(f"Error during topological sort: {e}")
        import traceback
        progress_callback(traceback.format_exc())
        return False

    # 4. Create Combined File
    try:
        create_combined_file(sorted_files, output_path, project_root, progress_callback)
    except Exception as e:
        progress_callback(f"Error creating combined file: {e}")
        import traceback
        progress_callback(traceback.format_exc())
        return False

    progress_callback(f"\nBundling process finished. Output: {output_path}")
    return True