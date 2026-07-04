# Xquik OpenAPI Example

Fetch Xquik's public OpenAPI document, inspect the generated raw tools, then
serve the curated MCP tools with an API key header when you execute
authenticated operations.

```bash
curl -fsSL https://xquik.com/openapi.json -o examples/xquik.openapi.json
mcp-curate parse examples/xquik.openapi.json
mcp-curate curate examples/xquik.openapi.json --max-tools 40
mcp-curate serve examples/xquik.openapi.json --curated --base-url https://xquik.com --header "x-api-key:$XQUIK_API_KEY"
```
