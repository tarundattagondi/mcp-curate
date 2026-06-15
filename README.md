# mcp-curate

[![CI](https://github.com/tarundattagondi/mcp-curate/actions/workflows/ci.yml/badge.svg)](https://github.com/tarundattagondi/mcp-curate/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Turn an OpenAPI spec into a *curated* MCP server an LLM can actually use — and prove it with an eval.**

A naive OpenAPI→MCP generator dumps one tool per endpoint. Point it at GitHub's
API and the model drowns in **1190 tools** and picks the wrong one. `mcp-curate`
consolidates those endpoints into a small set of clear, well-described
meta-tools — and ships an eval harness that measures whether the model picks the
right tool, raw vs curated, on *your own* spec.

## Before / after

| Spec | Raw tools | Curated tools | Reduction |
|------|----------:|--------------:|----------:|
| Swagger Petstore | 19 | **3** | 84% |
| Stripe API | 587 | **40** | 93% |
| GitHub REST API | 1190 | **40** | 97% |

```
$ mcp-curate curate examples/github.json
raw tools:     1190
curated tools: 40  (budget 40)
reduction:     97%

Curated tools (actions consolidated):
  - repos: 202 actions  [repos]
  - actions: 187 actions  [actions]
  - orgs: 108 actions  [orgs]
  - issues: 55 actions  [issues]
  ...
```

Each curated tool exposes an `action` argument that selects the underlying
operation, so 1190 flat choices become 40 namespaced ones.

**Oversized tags get split, not stuffed.** When the tool budget has headroom,
a giant tag is broken into focused sub-tools by path instead of one bloated
tool. With more budget, GitHub's 202-operation `repos` tag splits cleanly:

```
$ mcp-curate curate examples/github.json --max-tools 120 --max-actions 30
  - repos: ...            repos_branches, repos_commits, repos_collaborators,
  - repos_branches: 36    repos_comments, repos_compare, ... (focused sub-tools)
```

At a tight budget (the default 40), curation keeps tags whole and clean rather
than forcing unrelated tags together; raise `--max-tools` to trade tool count
for smaller, more focused tools.

## Does curation actually help? (the eval)

`mcp-curate eval` runs natural-language requests against both the raw and the
curated tool set using your LLM key, and reports how often the model routes to
the correct tool.

```
$ export ANTHROPIC_API_KEY=...
$ mcp-curate eval examples/stripe.json --cases examples/eval_cases/stripe.yaml

Eval: raw vs curated tool selection
cases: 11   raw tools: 587   curated tools: 40

raw     correct-tool selection: <run it>%
curated correct-tool selection: <run it>%
  -> improvement: <run it> points
```

The harness uses **your** key on **your** spec, so the numbers aren't
hard-coded — run the command above to reproduce them. Golden sets ship for
Petstore and Stripe (`examples/eval_cases/`); add your own as a small YAML file.

The eval is deliberately honest. Beyond correct-tool selection it also reports:

- **curated tool + action** accuracy — so curation can't "win" just by offering
  fewer, broader tools (it must still route to the right *operation*);
- **argument construction** accuracy (raw vs curated) — for cases that declare
  expected arguments, whether the model filled the right parameters
  (e.g. `petId: 42` from "look up pet 42").

## Install

```bash
git clone <repo> && cd mcp-curate
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,llm]"
./examples/fetch_specs.sh        # petstore is committed; this also grabs GitHub + Stripe
```

## Usage

```bash
# Inspect a spec's raw tool count.
mcp-curate parse examples/petstore.json

# See the before/after curation report.
mcp-curate curate examples/github.json --max-tools 40

# Serve the curated MCP server over stdio (bring-your-own auth header).
mcp-curate serve examples/petstore.json --curated \
  --header "Authorization: Bearer $TOKEN"

# A/B the tool selection with your LLM key.
mcp-curate eval examples/petstore.json --cases examples/eval_cases/petstore.yaml
```

Add `--llm-descriptions` to `curate`/`serve`/`eval` to let the LLM polish the
curated tool names and descriptions (otherwise they're generated deterministically,
with no API key required).

## How it works

1. **Parse** — load OpenAPI 3.x (JSON/YAML), resolve `$ref` with cycle cutting,
   flatten each operation into a spec-agnostic model.
2. **Curate** — group operations by tag (path-segment fallback), merge the
   smallest *related* groups to fit a tool budget, split any oversized group
   into focused sub-tools using leftover headroom, and collapse each group into
   one meta-tool with an `action` selector.
3. **Serve** — expose either tool set over the MCP stdio transport; tool calls
   become real HTTP requests against the spec's server URL.
4. **Eval** — force the model to pick a tool for each golden request and score
   raw vs curated routing.

## Security

Runs fully local; nothing leaves your machine except LLM calls (eval, with your
key) and the API calls your served spec makes. An **SSRF guard is on by default**
— tool calls to loopback/private/link-local hosts are blocked (the cloud-metadata
address `169.254.169.254` always), so a malicious spec can't exfiltrate your auth
headers. Use `--allow-local-network` to serve a localhost/private API. See
[SECURITY.md](SECURITY.md).

## Development

```bash
python -m pytest        # 35 tests: parser, curation, server roundtrip, eval
```

Tests are offline: the parser/curation suites need no network, and the eval
suite uses a scripted LLM client (no API key).

## License

MIT
