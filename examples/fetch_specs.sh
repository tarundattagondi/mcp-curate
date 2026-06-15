#!/usr/bin/env bash
# Fetch the demo specs used in the README and curation examples.
# Petstore is committed; GitHub's spec is large (~12 MB) and gitignored.
set -euo pipefail
cd "$(dirname "$0")"

curl -sL https://petstore3.swagger.io/api/v3/openapi.json -o petstore.json
echo "petstore.json: $(wc -c < petstore.json) bytes"

curl -sL \
  https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json \
  -o github.json
echo "github.json:   $(wc -c < github.json) bytes"

curl -sL https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json -o stripe.json
echo "stripe.json:   $(wc -c < stripe.json) bytes"
