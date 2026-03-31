# Docstring Rules

This repository uses Google-style docstrings.

The goals are:
- make interfaces understandable without reading all call sites
- explain intent, not just restate type hints
- document architecture boundaries clearly
- keep docstrings consistent across shared platform code and concrete agents

## 1. File-Level Docstrings

Every Python file should start with a module docstring in this format:

```python
"""Created: YYYY-MM-DD

Purpose: One concise sentence describing the file's responsibility.
"""
```

Rules:
- place it at the very top of the file
- keep the purpose sentence short and specific
- describe the file's responsibility, not its entire implementation

## 2. Class Docstrings

Add a class docstring when the class is:
- public
- architectural
- non-obvious
- reused across modules

The class docstring should answer:
- what this class is
- what role it plays in the architecture
- what it is responsible for
- what it is *not* responsible for, when that distinction matters

Good example themes:
- “this is one storage layer”
- “this orchestrates multiple layers”
- “this is working memory, not long-term memory”

Avoid:
- repeating field names line by line
- saying only “Represents X” when the behavior is non-trivial

## 3. Method Docstrings

Use Google-style sections:

```python
def method(arg: str) -> int:
    """Short summary sentence.

    Longer explanation when needed.

    Args:
        arg: What the argument means in this system.

    Returns:
        What the method returns and any important behavior.

    Raises:
        ValueError: When the input is invalid.
    """
```

Add method docstrings when the method:
- is public
- participates in architecture or business logic
- has side effects
- is easy to misuse

Private helpers do not always need docstrings. Add them only when their role is
not obvious from the name and body.

## 4. Prefer Explaining Intent

Bad:
- “Stores a value.”
- “Gets the item.”

Better:
- explain where the value is stored
- explain ordering, promotion, caching, archival, or fallback behavior
- explain why the method exists in the architecture

## 5. Don’t Repeat Type Hints

Bad:
- “session_id: A string.”

Better:
- “session_id: Identifier of the active conversation session.”

Type hints already describe the shape. The docstring should describe meaning.

## 6. Explain Boundaries

For architectural abstractions, explicitly document boundaries.

Examples:
- working memory vs long-term memory
- layer vs store
- planner vs agent
- shared platform vs concrete agent

This is important in this repository because many abstractions are similar on
the surface but have different responsibilities.

## 7. Keep Docstrings Accurate

If behavior changes:
- update the docstring in the same change
- do not leave stale architectural claims behind

Docstrings are part of the implementation contract.

## 8. Scope Priorities

Highest priority for docstrings:
- interfaces and abstract base classes
- orchestration code
- persistence layers
- planners
- tools
- agent entrypoints

Lower priority:
- trivial test helpers
- obvious one-line wrappers

## 9. Style Rules

- use complete sentences
- keep the first line short
- avoid marketing language
- avoid vague words like “handles stuff”
- be concrete and technical
- use backticks for code identifiers when helpful

## 10. Practical Standard for This Repo

At minimum, every important module should have:
- file-level docstring
- class docstring for public classes
- method docstrings for public methods

Especially for shared platform code under `src/`, assume the next engineer does
not know the architecture yet. Write the docstring so they can understand the
role of the abstraction before reading its implementation.
