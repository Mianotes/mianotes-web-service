# Code Review Skill

## Purpose

Use this skill to review code for correctness, maintainability, clarity, security, typing, documentation, and modern best practices.

The goal is to give practical review feedback that helps the user improve the code without rewriting everything unless they ask for that.

## When to use this skill

Use this skill when the user asks to:

* Review code
* Check code quality
* Check Python code
* Check PEP8 compliance
* Review a pull request
* Improve code structure
* Validate type hints
* Find bugs or anti-patterns
* Suggest refactoring
* Check whether code follows best practices

## Review priorities

Review the code in this order:

1. Correctness
2. Security
3. Error handling
4. Maintainability
5. Type safety
6. Readability
7. Performance
8. Documentation
9. Formatting and style

Do not focus on style before checking whether the code works.

## Review approach

### 1. Understand the context

Before reviewing, identify:

* The language and framework
* The code's purpose
* Whether it is application code, library code, scripts, tests, or infrastructure code
* Any version constraints
* Any project conventions already visible in the code

Do not invent project rules that are not present.

### 2. Check correctness

Look for:

* Logic errors
* Missing edge cases
* Incorrect assumptions
* Invalid return values
* Race conditions
* Incorrect async or concurrency handling
* Broken control flow
* Incorrect data transformations
* State that can become inconsistent

### 3. Check error handling

Look for:

* Bare exceptions
* Swallowed errors
* Missing validation
* Weak retry logic
* Unclear error messages
* Resource leaks
* Failure paths that leave the system in a bad state

Prefer specific exceptions and clear recovery behaviour.

### 4. Check security

Look for:

* Unsafe input handling
* Hardcoded secrets
* Insecure file handling
* Shell injection risks
* SQL injection risks
* Missing authentication or authorisation checks
* Excessive permissions
* Sensitive data in logs
* Unsafe deserialisation

Raise security issues as critical when they can expose data, credentials, systems, or users.

### 5. Check maintainability

Look for:

* Large functions
* Deep nesting
* Duplicated logic
* Hidden side effects
* Unclear naming
* Tight coupling
* Global state
* Functions doing too much
* Code that is hard to test

Prefer small, clear functions with explicit inputs and outputs.

### 6. Check typing

For Python, prefer:

* Type hints on public functions
* Return type annotations, including None
* Modern syntax such as list[], dict[], and str | None
* Specific types instead of Any
* Clear dataclass, TypedDict, Protocol, or Pydantic usage when useful

Flag missing or weak typing when it makes the code harder to maintain.

### 7. Check Python style

For Python code, check:

* PEP8 conventions
* 88 character line length
* 4 spaces for indentation
* snake_case for functions and variables
* PascalCase for classes
* UPPER_SNAKE_CASE for constants
* Imports grouped as standard library, third-party, local
* No wildcard imports
* No unused imports
* f-strings instead of older formatting where suitable
* pathlib instead of os.path where suitable
* context managers for files, locks, and connections

### 8. Check common Python issues

Look for:

* Mutable default arguments
* Bare except clauses
* Overuse of global
* Manual file handling without with
* Overuse of Any
* Old typing imports when modern syntax is available
* Complex list or dict comprehensions that reduce readability
* Repeated code that should become a helper
* Functions with too many branches
* Blocking calls inside async functions

### 9. Check documentation

Review:

* Public functions and classes for docstrings
* Complex logic for comments
* README or usage notes when needed
* Error behaviour documentation
* Missing examples for non-obvious APIs

Do not ask for comments that repeat obvious code.

## Output format

Use this format when reviewing code:

# Code Review

## Summary

Give a short summary of the code quality and the main risks.

## Findings

### Critical

Use this section for bugs, security problems, data loss risks, broken logic, or production issues.

Format each item like this:

* File or line:
* Issue:
* Why it matters:
* Suggested fix:

### Important

Use this section for maintainability, typing, error handling, or design issues that should be fixed soon.

Format each item like this:

* File or line:
* Issue:
* Why it matters:
* Suggested fix:

### Minor

Use this section for style, naming, formatting, and small improvements.

Format each item like this:

* File or line:
* Issue:
* Suggested fix:

## Positive notes

Mention what the code does well, but keep it short and specific.

## Suggested patch

Only include a patch when the fix is clear and small.

If the user asks for a rewrite, provide the improved version.

## Tooling suggestions

For Python projects, suggest these commands when relevant:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```

Only suggest tools that fit the project.

## Review rules

* Be direct and practical.
* Do not rewrite code unless asked.
* Do not over-focus on style.
* Do not suggest large architecture changes unless the code needs them.
* Do not invent missing requirements.
* When unsure, state the assumption.
* Prioritise fixes that reduce real risk.
* Use examples only when they make the fix clearer.
* Keep feedback short enough to act on.
* Group repeated issues instead of listing every instance.
* Prefer clear fixes over vague advice.

## Severity guide

Use Critical for:

* Security vulnerabilities
* Data loss
* Broken logic
* Crashes in normal use
* Incorrect permissions
* Race conditions
* Production blockers

Use Important for:

* Weak error handling
* Hard-to-maintain structure
* Missing tests around risky code
* Missing or misleading types
* High complexity
* Duplicated logic
* Fragile assumptions

Use Minor for:

* Naming
* Formatting
* Small readability improvements
* Import order
* Simple documentation gaps
* Style issues

## Python examples to recognise

### Mutable default argument

Bad:

```python
def add_item(item: str, items: list[str] = []) -> list[str]:
    items.append(item)
    return items
```

Good:

```python
def add_item(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

### Bare exception

Bad:

```python
try:
    risky_operation()
except:
    pass
```

Good:

```python
try:
    risky_operation()
except ValueError as error:
    logger.error("Invalid value: %s", error)
    raise
```

### Manual file handling

Bad:

```python
file = open("data.txt")
data = file.read()
file.close()
```

Good:

```python
from pathlib import Path

data = Path("data.txt").read_text()
```

### Missing type hints

Bad:

```python
def process(data):
    return data.upper()
```

Good:

```python
def process(data: str) -> str:
    return data.upper()
```
