# Docstring Rules

This repository uses Google-style docstrings.

Goals:

- make interfaces understandable without reading all call sites
- explain intent, not just restate type hints
- document architecture boundaries clearly
- keep docstrings consistent across shared platform code and concrete agents

## File-Level Docstrings

Every Python file should start with:

```python
"""Created: YYYY-MM-DD

Purpose: One concise sentence describing the file's responsibility.
"""
```

## Class Docstrings

Add class docstrings for:

- public classes
- architectural classes
- reused abstractions
- non-obvious classes

They should explain:

- what the class is
- what role it plays
- what it is responsible for
- what it is not responsible for when that distinction matters

## Method Docstrings

Use Google-style sections:

```python
def method(arg: str) -> int:
    """Short summary sentence.

    Args:
        arg: What the argument means in this system.

    Returns:
        What the method returns.
    """
```

## Style Rules

- use complete sentences
- keep the first line short
- avoid vague wording
- do not repeat type hints
- explain architecture boundaries when relevant

## Priority Areas

Highest priority:

- interfaces and abstract bases
- orchestration code
- persistence layers
- planners
- tools
- agent entrypoints
