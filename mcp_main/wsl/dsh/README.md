# DSH runtime-prompt companion

`runtime-prompt-companion.js` is generated from
`mcp_main.win.mcp.runtime_prompt` for DSH releases whose MCP client registers
tools but does not project `initialize.instructions` into the model system
prompt.

## Generate and verify

```bash
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py --check
python3 -m unittest dev.tests.test_runtime_prompt -v
```

Never edit the generated JavaScript. The MCP Engine and DSH companion must be
deployed from the same checkout so their prompt revision cannot drift.

## Install

Install `@deepseek-ai/dsh-mcp-client` in the target DSH profile, then merge the
two entries from `cordis.patch.yml.example` into that profile's
`cordis.patch.yml`, replacing `<repo>` with the absolute WSL checkout path. The
MCP client owns tools and reconnect behavior; the companion contributes only
the namespaced `mcp:onshape:runtime-policy` system-prompt section.

Treat the two entries as one deployment unit. On update or rollback, switch the
Windows Engine, WSL checkout, generated companion, and DSH profile generation
together. The Operator verification must prove both a tool call and prompt
visibility from an external cwd before declaring the client compatible.
