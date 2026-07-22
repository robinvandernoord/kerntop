# Code style

- Import typing as `import typing as t`, then use qualified names such as
  `t.Any` and `t.Iterable`.
- Do not annotate values with bare `object`; use the actual type or `t.Any`.
- Do not make parameters with defaults keyword-only using `*`.
- Pass optional arguments by keyword at call sites.
- Precompile regular expressions at module scope.
- Use `elif` for mutually exclusive branches when it improves clarity.

# Workflow

- Make file edits with the patch tool and keep each patch to one file.
- Do not add or run tests unless explicitly requested.
