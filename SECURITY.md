# Security

`mcp-curate` runs entirely on your machine and never transmits your data to a
third party, with two deliberate exceptions you control:

- **The eval / `--llm-descriptions`** send tool names, descriptions, and your
  natural-language test requests to the LLM provider (Anthropic by default),
  authenticated with **your** `ANTHROPIC_API_KEY` (read from the environment,
  never logged or committed).
- **`serve`** makes HTTP requests to the API described by your spec, using the
  auth headers you pass via `--header`.

## Threat model & built-in protections

The main risk in any "OpenAPI → live server" tool is that a **malicious or
mistaken spec** points its server URL somewhere it shouldn't, and tool calls
then send your auth headers there.

mcp-curate mitigates this:

- **SSRF guard (on by default).** Outbound tool-call requests are blocked if the
  target resolves to a non-public address — loopback, private ranges, or
  link-local. The cloud-metadata endpoint (`169.254.169.254`) is **always**
  blocked, even with the opt-in below. See `server/safety.py`.
- **No redirect following.** A redirect can't bounce a request (with your
  headers) to an unchecked host.
- **Local/JSON-only parsing.** Specs are parsed with `yaml.safe_load` (no
  arbitrary object construction) and only local `#/...` `$ref`s are resolved —
  the parser never fetches remote references.
- **Data-only deserialization.** Spec files and exported tool sets
  (`curate --export`) are parsed as plain JSON/YAML — never `pickle`, `eval`, or
  arbitrary object construction. A corrupt or hand-edited export fails with a
  clean error instead of executing anything. The SSRF guard above applies to a
  served export exactly as to a spec, so a malicious export's server URL cannot
  reach an internal/metadata host either.
- **Path-parameter encoding.** Values substituted into URL paths are
  percent-encoded, preventing path/segment injection.
- **Request timeouts** are set on every call.

### Serving a localhost or private API

If you intentionally serve a spec whose API runs on `localhost` or a private
network, opt in explicitly:

```bash
mcp-curate serve ./my-spec.yaml --curated --allow-local-network \
  --header "Authorization: Bearer $TOKEN"
```

This permits loopback/private hosts but still blocks the cloud-metadata range.

## Residual risks (your responsibility)

- **Only serve specs you trust.** A trusted-looking but malicious public host in
  a spec will still receive the auth headers you configured — that is inherent to
  calling an API. Review a spec's `servers:` URL before serving it.
- DNS rebinding is not fully mitigated (addresses are checked at request time,
  not pinned). For untrusted specs, prefer reviewing the host first.
- A maliciously crafted spec could be very large or deeply nested and exhaust
  memory/CPU while parsing (a denial-of-service against your own process). The
  parser caps `$ref` recursion depth and cuts cycles, but does not bound total
  document size. Don't parse specs you don't trust without resource limits.

## Reporting

Found a vulnerability? Please open a private security advisory on the GitHub
repository rather than a public issue.
