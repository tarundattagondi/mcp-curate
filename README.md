# mcp-curate

Turn an OpenAPI spec into a **high-quality** MCP server — not a 1-to-1 dump of
every endpoint, but a small set of clear, well-described tools an LLM can
actually choose between. Ships with an eval harness that proves the curation
helps.

> Status: under construction. Phase 1 (baseline parser + stdio server) is done;
> curation (Phase 2) and the eval harness (Phase 3) are in progress.

## Install

```bash
pip install -e ".[dev]"
```

## Usage (Phase 1)

```bash
# Inspect a spec and see the raw tool count.
mcp-curate parse examples/petstore.json
mcp-curate parse examples/github.json     # 1190 operations -> 1190 raw tools

# Run the raw MCP server over stdio (bring-your-own auth headers).
mcp-curate serve examples/petstore.json --header "Authorization: Bearer $TOKEN"
```

## Development

```bash
python -m pytest
```

## License

MIT
