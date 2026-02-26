# Legacy Agent Translate Page

This folder contains frozen reference copies of the pre-rewrite
`agent_translate_page` implementation.

Purpose:

- preserve legacy behavior as a read-only reference while rebuilding workflow logic
- support side-by-side comparison during the refactor

Files:

- Legacy modules were removed once replaced in active workflow code.
- This folder remains as a marker that legacy freeze/cutover happened.

Notes:

- Do not route production execution through these modules.
- Avoid editing unless needed for reference clarity.
