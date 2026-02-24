# Recipe Identifier Parsing Enhancement

## Current State

The `Recipe` class currently has these attributes related to naming:

- **`recipe.name`**: Recipe name without extension (e.g., `"Firefox.upload.jamf"`)
- **`recipe.identifier`**: Currently returns the same as `recipe.name`
- **`recipe.short_name`**: First part before dot (e.g., `"Firefox"`)
- **`recipe.filename`**: Reserved for future use - will store full filename with extension

## Problem

The `recipe.identifier` property currently returns the filename-based name (e.g., `"Firefox.upload.jamf"`), but it **should** return the actual `Identifier` field from inside the recipe file, which uses reverse notation (e.g., `"com.github.autopkg.download.Firefox"`).

This is important because:

1. **Logging**: Messages should show the canonical recipe identifier for clarity
1. **Git commits**: Trust update commit messages should reference the proper identifier
1. **Notifications**: Slack/GitHub notifications should use the official identifier
1. **Reporting**: Reports should track recipes by their canonical identifier

## Solution Design

### 1. Add Identifier Parsing

Parse the recipe file (plist or YAML) to extract the `Identifier` field:

```python
def _parse_identifier_from_file(self, recipe_path: Path) -> str | None:
    """Parse the Identifier field from a recipe file.

    Args:
        recipe_path: Path to the recipe file

    Returns:
        The recipe identifier from the file, or None if not found
    """
    try:
        if recipe_path.suffix == ".yaml":
            from ruamel.yaml import YAML

            yaml = YAML(typ="safe")
            with open(recipe_path, encoding="utf-8") as f:
                recipe_data = yaml.load(f)
        else:  # .plist or .recipe
            with open(recipe_path, "rb") as f:
                recipe_data = plistlib.load(f)

        return recipe_data.get("Identifier")
    except Exception as e:
        logging.debug(f"Failed to parse identifier from {recipe_path}: {e}")
        return None
```

### 2. Lazy Loading Strategy

To avoid performance impact, use lazy loading with caching:

```python
class Recipe:
    def __init__(self, name: str, post_processors: list = None):
        self.name = name
        self._cached_identifier = None  # Cache the parsed identifier
        self._identifier_loaded = False  # Track if we've tried loading
        # ... rest of init

    @property
    def identifier(self):
        """Get the recipe identifier.

        Parses the actual Identifier field from the recipe file in reverse
        notation (e.g., "com.github.autopkg.download.Firefox"). Falls back
        to recipe.name if parsing fails.

        Returns:
            str: Recipe identifier from file, or recipe name as fallback
        """
        if not self._identifier_loaded:
            # Only try to load once
            self._identifier_loaded = True

            # Find the recipe file
            recipe_path = self._find_recipe_file_path(args)  # Need args!
            if recipe_path:
                parsed = self._parse_identifier_from_file(recipe_path)
                if parsed:
                    self._cached_identifier = parsed

        return self._cached_identifier or self.name
```

### 3. Challenge: Args Availability

The main challenge is that `_find_recipe_file_path()` needs `args` to locate the recipe file, but the `identifier` property doesn't have access to `args`.

**Options:**

**Option A: Pass args to Recipe init**

```python
class Recipe:
    def __init__(self, name: str, args, post_processors: list = None):
        self.name = name
        self.args = args  # Store args for later use
        # ...
```

- **Pro**: Clean, args available when needed
- **Con**: Breaks existing Recipe construction, requires updates everywhere

**Option B: Load identifier explicitly with a method**

```python
def load_identifier(self, args):
    """Explicitly load the identifier from the recipe file."""
    if not self._identifier_loaded:
        recipe_path = self._find_recipe_file_path(args)
        # ... parse and cache


# Usage:
recipe = Recipe("Firefox.upload.jamf")
recipe.load_identifier(args)
print(recipe.identifier)  # Now has the real identifier
```

- **Pro**: Doesn't break existing code
- **Con**: Requires explicit call, easy to forget

**Option C: Make identifier a method that takes args**

```python
def identifier(self, args=None):
    """Get the recipe identifier."""
    if args and not self._identifier_loaded:
        # Try to load real identifier
        recipe_path = self._find_recipe_file_path(args)
        # ... parse and cache
    return self._cached_identifier or self.name
```

- **Pro**: Flexible, backwards compatible if args optional
- **Con**: Awkward API (properties shouldn't take args)

### 4. Recommended Approach

**Hybrid approach:**

1. Keep `recipe.identifier` as a simple property that returns cached value or falls back to `recipe.name`
1. Add `recipe.load_metadata(args)` method called early in the workflow
1. This method loads identifier, filename, and any other metadata from the file

```python
class Recipe:
    def __init__(self, name: str, post_processors: list = None):
        self.name = name
        self.filename = None  # Set by load_metadata()
        self._identifier = None  # Set by load_metadata()
        # ...

    @property
    def identifier(self):
        """Recipe identifier (reverse notation if loaded, else name)."""
        return self._identifier or self.name

    def load_metadata(self, args):
        """Load recipe metadata from the recipe file.

        Populates:
        - self._identifier: Reverse notation identifier
        - self.filename: Full filename with extension
        """
        recipe_path = self._find_recipe_file_path(args)
        if not recipe_path:
            return

        # Store filename
        self.filename = recipe_path.name

        # Parse identifier
        self._identifier = self._parse_identifier_from_file(recipe_path)


# Usage in main workflow:
recipe_list = parse_recipe_list(...)
for recipe in recipe_list:
    recipe.load_metadata(args)  # Load once at the start
    # Now recipe.identifier has the real value
```

## Implementation Steps

1. **Add `_parse_identifier_from_file()` method** to Recipe class
1. **Add `load_metadata()` method** to Recipe class
1. **Update main workflows** to call `load_metadata()` after recipe creation:
   - In `main()` after `parse_recipe_list()`
   - In `update_trust_only_workflow()`
1. **Update tests** to verify identifier parsing
1. **Document behavior** in Recipe class docstring

## Testing Strategy

Create test recipe files with known identifiers:

```python
def test_identifier_parses_from_yaml_recipe():
    """Test parsing identifier from YAML recipe file."""
    # Create temp recipe file with Identifier field
    recipe_yaml = """
    Identifier: com.github.autopkg.download.Firefox
    Description: Downloads Firefox
    Input:
      NAME: Firefox
    Process:
      - Processor: EndOfCheckPhase
    """

    recipe = Recipe("Firefox.download")
    recipe.load_metadata(args)  # args points to temp recipe
    assert recipe.identifier == "com.github.autopkg.download.Firefox"
    assert recipe.name == "Firefox.download"
```

## Performance Considerations

- **Lazy loading**: Only parse files when `load_metadata()` is called
- **Caching**: Parse once, cache result
- **Optional**: If performance is critical, could skip loading for recipes that don't need it

## Backwards Compatibility

- `recipe.identifier` continues to work, just returns better data
- Old code that doesn't call `load_metadata()` still works (falls back to `recipe.name`)
- No breaking changes

## Related Files

- `autopkg_wrapper/models/recipe.py` - Recipe class implementation
- `autopkg_wrapper/autopkg_wrapper.py` - Main workflow
- `autopkg_wrapper/utils/git_functions.py` - Uses identifier in commit messages
- `autopkg_wrapper/notifier/slack.py` - Uses identifier in notifications

## Estimated Effort

- **Complexity**: Medium
- **Time**: 2-3 hours
- **Testing**: 1 hour
- **Documentation**: 30 minutes

**Total**: ~4 hours
