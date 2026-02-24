# TODO

## High Priority

### Parse Actual Recipe Identifier from Recipe Files

Currently, `recipe.identifier` returns the recipe name (e.g., "Firefox.upload.jamf"). It should parse and return the actual `Identifier` field from inside the recipe file in reverse notation (e.g., "com.github.autopkg.download.Firefox").

**See:** [docs/recipe-identifier-parsing.md](docs/recipe-identifier-parsing.md)

**Status:** Not started
**Complexity:** Medium
**Impact:** Improves accuracy of logging and reporting

## Medium Priority

_No items currently_

## Low Priority

_No items currently_

## Completed

- ✅ Add `--update-trust-only` feature with glob pattern support
- ✅ Simplify `getattr` usage with args defaults
- ✅ Fix empty environment variable handling
- ✅ Refactor Recipe class naming for clarity (`filename` → `name`)
