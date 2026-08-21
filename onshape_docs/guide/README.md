# Task guides

Guides describe supported workflows: what to do, in what order, and which tool
to call. Search the project-doc index before reading a whole guide.

| Guide | Use it for |
|---|---|
| `feature-script.md` | FeatureScript lookup, version checks, exact symbol detail, and local validation order |
| `rest-api.md` | REST reference tiers, endpoint/schema lookup, auth, errors, and quota-aware operation planning |
| `mcp-server.md` | MCP setup, tool boundaries, mutation confirmation, outputs, and offline tests |

The required lookup sequence is:

1. `docs_search` or `docs_list` to identify the page and section.
2. `docs_section` to read only that section.
3. Use the domain index named by the guide (`fs_search`, `onshape_api_search`, and related detail tools).
4. Read a complete markdown or raw source only when indexed detail is insufficient.

Observed behavior and hard-won lessons belong in `onshape_docs/experience/`.
Experiment records and integrity evidence belong in
`onshape_docs/verification/`.
