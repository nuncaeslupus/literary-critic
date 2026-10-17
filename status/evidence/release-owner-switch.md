# Release T10 — owner switch

Gate: `dev_config_entries == 0`. Recorded 2026-10-17 on the owner's Windows 11 Pro PC.

## Extension installed

**Installed: yes** — literary-critic 0.1.2 (`.mcpb` from the GitHub release),
through Settings → Extensions. What the app showed, in order:

- A red banner: installing grants the extension access to everything on the
  computer, and developer information is not verified by Anthropic.
- A Windows dialog, "Install Extension?", saying it fetches dependencies and may
  take a few minutes.
- "All requirements met"; version 0.1.2, author nuncaeslupus, Apache-2.0.
- No SmartScreen or Defender warning.

Settings left at their defaults: *Your novels' folder* empty (on purpose, to test
the shared `folders.json`), *Update automatically* on. Tool permissions:
interactive tools (2: places, change card) "Needs approval", read-only tools (6).

The separate doc-control extension (0.8.3) stays installed: literary-critic bundles
its own doc-control; the separate one serves other documents.

## Dev entry removed

The `literary-critic-dev` entry (uv running `lc mcp` from the clone) was removed
through Settings → Developer → Local MCP servers (trash icon).
`claude_desktop_config.json` afterwards: `"mcpServers": {}`.

dev_config_entries: 0

## Works still found

After a full quit and restart, a new chat asked which novels there are and which
version runs. The first call showed the approval prompt "Claude wants to use
Works from Literary Critic" (Decline / Always allow / Allow once); after
*Allow once* the answer listed the owner's novel with its folder and last-used
date (2026-10-16), literary-critic 0.1.2 ("the latest, no update pending") and
doc-control 0.8.3. The novel was found through the shared `folders.json`, with
the extension's folder setting empty.

works_found: 1
