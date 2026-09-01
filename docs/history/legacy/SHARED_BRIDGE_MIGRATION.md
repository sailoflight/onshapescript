# Shared WIN-WSL MCP bridge migration record

> **Historical, non-executable record.** The project-owned relay described below
> was retired after the independent shared bridge passed acceptance. Referenced
> relay/listener/launcher files are intentionally absent and their commands are
> unsupported. Current authority is `../../operations/MCP_RUNBOOK.md`; archive
> routing is maintained in `../TRACEABILITY.md`.

## Status

This document records the integration and migration boundary used to extract the
independent `win-wsl-mcp-bridge`. The shared bridge now exists as a separate
project with two components, bidirectional logical streams, per-host SQLite
registries, and a peer-only Registry MCP.

The project-owned Onshape bridge under `mcp_main/wsl/` and
`mcp_main/win/bridge/` was retired after acceptance. Its executable source paths
were removed; the remaining sections retain the original plan and acceptance
criteria as historical evidence.

## Goal

A business MCP remains an ordinary MCP with no WIN-WSL-specific implementation:

```text
local MCP client <-> standard MCP stdio <-> business MCP
```

When a client runs in WSL and the MCP runs on Windows, an independently deployed
bridge makes both sides observe the same local relationship:

```text
WSL agent/client
  -> shared WSL relay
  -> local-only WIN-WSL transport
  -> shared Windows relay
  -> standard MCP stdio
  -> business MCP
```

The business MCP does not know that its client is in WSL. The WSL client sees
the original MCP initialization, identity, capabilities, instructions, tools,
results, errors, cancellation, and notifications rather than a rewritten
business API.

## Design principles

1. **Business MCPs are transport-neutral.** They contain no project-specific WSL
   relay, bridge control script, TCP port, client profile patch, or Windows task
   installer.
2. **The bridge is separately deployable infrastructure.** One shared bridge
   implementation serves registered MCPs; projects do not copy it.
3. **One physical bridge may carry multiple logical MCPs.** Each registered MCP
   retains its own identity, instructions, schemas, errors, and diagnostic
   boundary. The bridge does not flatten all tools into one business MCP.
4. **The registry describes; the MCP owns behavior.** Process limits, persistent
   resources, and multi-process support belong to the business MCP contract and
   must be enforced by that MCP when required. The bridge reports those
   capabilities but does not invent lifecycle guarantees.
5. **Local communication is the security boundary.** The Windows relay listens
   only on the local WIN-WSL path and communicates only with the local WSL
   relay. It never exposes a public listener.
6. **Reuse precedes replacement.** Extraction starts from the current byte relay,
   loopback transport, hidden Windows launchers, logging, and reconnect behavior.
   Project-specific dispatch and names are removed rather than rebuilding the
   transport from scratch.

## Non-goals

The shared bridge does not:

- make a business MCP portable when its own handlers require a specific OS;
- guarantee that a business MCP is safe to run more than once;
- serialize business operations to compensate for a missing process lock;
- merge unrelated runtime policies into one authority;
- expose arbitrary Windows command execution to WSL agents;
- own business credentials, browser profiles, domain state, or cloud permissions;
- reinterpret a successful TCP connection as successful MCP initialization.

A browser MCP may still require Windows. Portability here means that its MCP
protocol and repository do not contain a special WSL client half; deployment
selection belongs to the external registry.

## Components

### WSL relay

The WSL relay is the only WSL runtime supplied by the shared bridge package. It:

- provides standard stdio MCP endpoints to local clients;
- selects a registered MCP by stable registry id;
- carries raw MCP traffic over the local bridge transport;
- keeps stdout MCP-only and sends diagnostics to stderr;
- reconnects the transport without changing business messages;
- exposes the read-only Registry MCP;
- projects downstream runtime instructions for clients that do not natively
  consume `initialize.instructions`.

A client may register several logical MCPs with the same relay executable:

```toml
[mcp_servers.onshape]
command = "win-wsl-mcp"
args = ["connect", "onshape"]

[mcp_servers.taobao]
command = "win-wsl-mcp"
args = ["connect", "taobao"]
```

These entries are logical endpoints, not copied WSL implementations in the
business repositories.

### Windows relay

The Windows relay is installed once with the shared bridge. It:

- accepts only the local WSL relay transport;
- resolves a stable registry id to an allowlisted local MCP entry;
- connects the selected MCP through standard stdio;
- forwards protocol bytes and keeps stderr out of MCP stdout;
- records bridge and registration diagnostics without taking ownership of
  business logs;
- rejects unknown registry ids and caller-supplied commands or arguments.

Starting a configured stdio process is a transport action, not a declaration
that the bridge owns its lifecycle semantics. If an MCP forbids multiple
processes, the MCP must say so in its capability summary and enforce its own
single-process lock or local resource ownership rule.

### Business MCP

A registered business MCP owns:

- its standard MCP entrypoint and supported protocol versions;
- `serverInfo`, capabilities, runtime instructions, schemas, and handlers;
- process and concurrency restrictions;
- persistent resources and their locks;
- credentials, domain state, costs, confirmation, and mutation gates;
- local diagnostics and recovery behavior.

It must be possible to invoke the same entrypoint from a local MCP client without
the shared bridge. No import from the shared bridge is required.

## Registry

The bridge registry is infrastructure metadata, separate from business MCP
source. Each host owns a separate local SQLite database for MCPs installed on
that host:

```text
Windows: %LOCALAPPDATA%\WinWslMcpBridge\registry.sqlite3
WSL:    $XDG_STATE_HOME/win-wsl-mcp-bridge/registry.sqlite3
        or ~/.local/state/win-wsl-mcp-bridge/registry.sqlite3
```

The databases are not shared through `/mnt/c`, UNC, or another cross-OS
filesystem. Private commands, args, cwd, env, credentials, and database paths
never cross the bridge or enter public Registry MCP results. A peer may select
only an existing registered id; it cannot submit launch data.

Local agents normally register local MCPs directly, so the public Registry MCP
exposes only the **peer** database's redacted summaries. It deliberately has no
`local|remote|all` aggregation switch. This avoids duplicate local capabilities
and prevents an agent from selecting the bridge for an MCP already available
locally.

Every registration provides a concise authored summary and may add observed MCP
metadata:

```yaml
id: onshape
name: Onshape MCP
summary: Onshape browser, FeatureScript, REST reference, and geometry tools
process:
  multiProcessAllowed: false
  enforcement: business-mcp
capabilityGroups:
  - browser
  - featurescript
  - rest-reference
  - geometry
```

`multiProcessAllowed` may remain null while metadata is unverified; the bridge
never defaults it to true. The business MCP owns and enforces the declaration.
Authored and observed metadata stay distinguishable, and downstream text remains
untrusted metadata rather than bridge instructions.

The peer-only Registry MCP exposes read-only discovery:

- `bridge_registry_list`
- `bridge_registry_search`
- `bridge_registry_describe`
- `bridge_registry_status`

Registration import, removal, command changes, and restart remain local Operator
operations, not ordinary registry tools.

A future opt-in capability-warehouse mode may cooperate with an external AI
capability repository so an Agent configures only the Bridge and loads selected
capabilities on demand. That mode is not current behavior. It requires stable
publisher/name/version identities, local-client inventory exchange for
deduplication, trust/signature policy, bounded on-demand schemas, and dynamic
client tool lifecycle. The two local SQLite databases remain deployment
authorities and never publish private launch configuration.

## Transport contract

One physical local transport may carry several logical streams in both
directions. The WSL relay establishes the full-duplex connection, but either
side may send a bounded `open` frame containing bridge protocol revision,
registered target id, and logical stream id. The receiving side resolves the id
in its own local database, acknowledges it, and then treats the stream as
ordinary MCP stdio bytes. Windows-to-WSL invocation therefore reuses the
WSL-initiated physical link and requires no second Windows-to-WSL connection.

The bridge protocol version is independent of the downstream MCP protocol
version. The bridge does not require a project-specific or patched MCP version.
MCP version negotiation continues between the client and business MCP through
the transparent stream.

Required transport behavior:

- bind only to the local WIN-WSL communication path;
- preserve byte order, message boundaries, EOF, cancellation, and notifications;
- keep stream ids and request ids isolated;
- bound handshake, connection, and idle failures;
- report `transport reachable`, `registry target resolved`, and `MCP initialized`
  as separate health states;
- never use a bare TCP connect as proof of MCP health;
- never log business payloads or secrets by default.

## Artifact workspace delivery

A host-local path returned by a remote MCP is not a transferable capability. The
shared bridge never scans tool text or JSON for paths and never lets an Agent
request an arbitrary peer file. Small content remains MCP-native inline or
`resources/read`; durable generated files use the bridge's negotiated
`artifacts/1` workspace-push extension.

A file-capable business MCP opts in through its private registration. For each
logical stream the bridge creates a private stage and publisher token. The MCP
writes one completed regular file there and explicitly publishes it. The bridge
snapshots from one opened handle, enforces source type and byte limits, computes
SHA-256, transfers ordered chunks on the existing full-duplex link, and
atomically commits beneath an Operator-authorized receiving inbox. Publication
returns a standard `resource_link` for the already-local committed file, so the
Agent never fetches from the remote MCP.

Source paths never cross the link. Traversal, absolute/drive/UNC paths, symlinks,
reparse-like objects, devices, directories, detectable hardlinks, size overflow,
hash mismatch, and partial transfer fail closed. Version 1 has no resume.
Production acceptance additionally requires owner-authenticated local publisher
endpoints plus directory-handle-anchored workspace creation (`openat`-style on
WSL and reparse-point-safe Windows APIs); the standalone Linux simulation does
not claim those Windows guarantees. The standalone bridge's `MCP_COVERAGE.md` is the detailed capability and remaining-gap
authority; the current project-owned Onshape bridge does not yet implement this
extension.

## Runtime instructions and client adapters

The business MCP remains the canonical source of its
`initialize.instructions`. The bridge forwards them without rewriting their
business authority.

Clients with native MCP instruction support consume the forwarded result. For
DSH versions that register tools but do not project instructions, the shared WSL
adapter dynamically installs one namespaced prompt section per logical MCP:

```text
mcp:<registry-id>:runtime-policy
```

Reconnect atomically replaces the previous revision; disconnect removes it. A
business repository does not generate or install its own WSL companion after
migration.

The Registry MCP summary is discovery metadata and never substitutes for the
business MCP runtime instructions.

## Process and resource declarations

The bridge does not promise lifecycle semantics on behalf of an MCP. The public
capability summary must state constraints such as:

```yaml
process:
  multiProcessAllowed: false
  enforcement: business-mcp
```

The business MCP is responsible for making that statement true, for example by
an exclusive local lock around a browser profile. The relay forwards a startup
or lock failure as an MCP/transport error; it does not start a second instance,
queue business work, or silently change the declared model.

## Reuse of the current implementation

The extraction should reuse the current implementation in this order:

1. Generalize `mcp_main/wsl/facade/mcp_tcp_bridge.py` from a fixed port relay to a
   registered target relay while preserving its stdlib-only byte-pump behavior.
2. Generalize the Windows socket and logging portions of
   `mcp_main/win/bridge/bridge_server.py`; replace the in-process Onshape import
   with registry lookup plus standard MCP stdio forwarding.
3. Move hidden VBS/PowerShell launch and local status behavior into the shared
   bridge package once, with names and paths independent of Onshape or Taobao.
4. Replace per-project `wsl_bridge_ctl.sh` scripts with one shared control entry.
5. Replace per-project DSH companions with the shared dynamic instruction
   adapter.
6. Add the read-only Registry MCP without placing command execution in its public
   schema.

The current TCP health probe and synchronous project-owned dispatch are evidence
for migration, not interfaces that must be preserved.

## Current Onshape mapping and migration

Current implemented runtime:

```text
DSH/Codex
  -> mcp_main/wsl/mcp_bridge_entry.sh
  -> mcp_main/wsl/facade/mcp_tcp_bridge.py
  -> 127.0.0.1:8766
  -> mcp_main/win/bridge/bridge_server.py
  -> in-process Onshape MCP dispatch
```

Target runtime:

```text
DSH/Codex
  -> shared win-wsl-mcp connect onshape
  -> shared local transport
  -> shared Windows relay
  -> registered standard Onshape MCP stdio entry
```

Until target acceptance, current scripts, runbook, and deployment remain the
operational authority. After acceptance:

- remove project-specific WSL runtime and DSH companion files;
- remove project-specific Windows bridge launchers and listener;
- keep only the generic business MCP stdio entry in this repository;
- preserve the old implementation as bounded historical evidence if needed,
  outside runtime import and deployment paths;
- update the Operator runbook and compatibility evidence in the same change.

Do not delete the current bridge first and then use production as the migration
test environment.

## Acceptance

The independent shared bridge is accepted only when all of the following hold:

- one unchanged standard MCP entry passes the same initialize, list, call,
  cancellation, notification, error, and EOF checks locally and through the
  bridge;
- the business MCP reports the same identity, instructions, capabilities, and
  schemas on both paths;
- the Registry MCP lists, searches, describes, and reports status for registered
  MCPs without exposing launch paths, arguments, environment values, or secrets;
- a registration with `multiProcessAllowed: false` exposes that fact and the MCP
  itself rejects conflicting ownership;
- the Windows relay accepts only local WSL relay communication and never binds a
  public interface;
- unknown ids and caller-supplied launch data are rejected before process start;
- DSH dynamically projects and replaces each downstream prompt section;
- one failed MCP does not corrupt another logical stream;
- business repositories contain no project-specific WSL bridge runtime after
  migration;
- legacy and canonical per-project launch paths are retired from production with
  a documented rollback point.

## Documentation ownership

This file owns the target shared bridge contract and extraction boundary.

While the legacy Onshape bridge remains deployed:

- `docs/architecture/OVERVIEW.md` describes current project behavior and links
  this target;
- `docs/modules/mcp-main.md` owns current Onshape MCP entrypoints and migration
  exclusions;
- `docs/operations/MCP_RUNBOOK.md` remains the current Operator authority;
- `docs/verification/MCP_CLIENT_COMPATIBILITY.md` remains current client
  evidence.

When the shared bridge becomes an independent project, this specification moves
with it. This repository retains only a short integration contract and the
historical migration record.
