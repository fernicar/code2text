# Code2Text

A Python utility for bundling Python projects into a single text file, making it easier to share code with Large Language Models (LLMs) or for documentation purposes.

![app_capture](https://github.com/fernicar/code2text/blob/main/images/app_capture.png)

## Description

Code2Text analyzes a Python project starting from a main file, identifies all local dependencies (imported modules within the same project), and combines their source code into a single output text file. The files are ordered topologically, ensuring dependencies are listed before the files that import them.

This tool is particularly useful for:
- Preparing codebases for analysis by LLMs
- Sharing code snapshots with others
- Creating comprehensive documentation
- Archiving project states

## Features

- **Dependency Analysis**: Automatically detects and includes all local project dependencies
- **Topological Sorting**: Orders files so dependencies appear before the files that import them
- **Markdown Formatting**: Wraps each file in code blocks with clear start/end markers
- **Project Root Detection**: Automatically identifies the project root directory
- **Two Interfaces**: Choose between a GUI or command-line interface

## Installation

Clone the repository:

```bash
git clone https://github.com/fernicar/code2text.git
cd code2text
```

No additional dependencies are required beyond the Python standard library.

## Usage

### Command Line Interface

```bash
python code2text.py <main_python_file> [output_file]
```

Example:
```bash
python code2text.py my_project/main.py bundled_output.txt
```

If no output file is specified, the result will be saved as `combined_output.txt` in the current directory.

### Graphical User Interface

```bash
python main_gui.py
```

The GUI provides a simple interface to:
1. Select the main Python file
2. Choose the output file location
3. View the detected project root
4. Monitor the bundling process through a log window

## How It Works

1. **Project Root Detection**: Identifies the project root by looking for common markers like `.git`, `pyproject.toml`, etc.
2. **Dependency Analysis**: Parses Python imports using the AST (Abstract Syntax Tree) module
3. **Graph Building**: Constructs a dependency graph where each file points to its dependencies
4. **Topological Sort**: Orders files so dependencies come before the files that import them
5. **File Combination**: Combines all files into a single output with clear markers

## Output Format

The output file contains all project files wrapped in Markdown code blocks with clear start/end markers:

```
# Start of path/to/file.py
[file content]
# End of path/to/file.py
```

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/fernicar/code2text/blob/main/LICENSE) file for details.

## Acknowledgments

* Special thanks to ScuffedEpoch for the [TINS](https://github.com/ScuffedEpoch/TINS) methodology and the initial example.
