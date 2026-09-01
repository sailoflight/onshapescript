# DSH runtime-prompt companion

`runtime-prompt-companion.js` is generated from
`mcp_main.win.mcp.runtime_prompt` for DSH releases whose MCP client registers
tools but does not project `initialize.instructions` into the model system
prompt.

## Generate and verify

```bash
python3 mcp_main/dsh/build_runtime_prompt_companion.py
python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
python3 -m unittest dev.tests.test_runtime_prompt -v
```

Never edit the generated JavaScript. The ordinary MCP and DSH companion must be
deployed from the same checkout so their prompt revision cannot drift.

## Install

Install `@deepseek-ai/dsh-mcp-client` in the target DSH profile, register the
ordinary Windows stdio MCP with the independently installed
`win-wsl-mcp-bridge`, then merge the two entries from
`cordis.patch.yml.example`. Replace `<bridge-client>` with the installed WSL
bridge client path and `<repo>` with this checkout path.

The shared bridge owns cross-host transport, registry, process lifecycle, and
loopback listeners. This repository owns no relay/listener/launcher. The MCP
client contributes tools; the companion contributes only the namespaced
`mcp:onshape:runtime-policy` system-prompt section. Treat them as one deployment
generation and verify a tool call plus prompt visibility from an external cwd.
