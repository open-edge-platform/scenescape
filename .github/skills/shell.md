# Shell Scripting Standards for SceneScape

## Shebang

Use `#!/usr/bin/env bash` for portability:

```bash
#!/usr/bin/env bash
```

Not `#!/bin/bash` (less portable) or `#!/bin/sh` (POSIX only, limiting).

## Code Style

### Linting

- **Linter**: shellcheck with style warnings
- **Command**:
  ```bash
  make lint-shell         # Lint all .sh files
  ```

### Indentation

- Use **2 spaces** (never tabs)
- Consistent with project standards

### Line Length

- Target: 80-100 characters for readability
- Break long commands with `\` line continuation

```bash
if [[ condition ]]; then
  echo "Indented with 2 spaces"
  if [[ nested ]]; then
    echo "Nested indentation"
  fi
fi
```

## Best Practices

### Exit on Error

Use `set -e` to exit on any error:

```bash
#!/usr/bin/env bash
set -e  # Exit immediately if a command fails
set -o pipefail  # Fail if any command in pipeline fails

# Now any failing command will exit the script
command1
command2
command3
```

### Strict Mode

For critical scripts, use strict mode:

```bash
set -euo pipefail
# -e: exit on error
# -u: exit on undefined variable
# -o pipefail: fail on pipe errors
```

### Trap Errors

Clean up on exit or error:

```bash
cleanup() {
  echo "Cleaning up..."
  rm -f /tmp/tempfile
}

trap cleanup EXIT
trap 'echo "Error on line $LINENO"' ERR
```

## Variables

### Naming

- **Local variables**: `lowercase_with_underscores`
- **Environment/Global**: `UPPERCASE_WITH_UNDERSCORES`
- **Read-only**: `readonly CONSTANT_VALUE`

```bash
# Local
local temp_file="/tmp/data"
local count=0

# Global/Environment
WORKSPACE_DIR="/workspace"
export DATABASE_PASSWORD

# Constants
readonly MAX_RETRIES=3
```

### Quoting

Always quote variables to prevent word splitting:

```bash
# Good
file_path="/path/with spaces/file.txt"
cat "$file_path"

# Bad - breaks with spaces
cat $file_path
```

### Default Values

```bash
# Use default if variable is unset
config_file="${CONFIG_FILE:-/etc/default.conf}"

# Use default if variable is unset or empty
database="${DATABASE_NAME:=scenescape}"

# Error if variable is unset
required="${REQUIRED_VAR:?Error: REQUIRED_VAR must be set}"
```

## Conditionals

### Use `[[ ]]` for Tests

Prefer `[[ ]]` over `[ ]` or `test`:

```bash
# Good - modern test
if [[ -f "$file" ]]; then
  echo "File exists"
fi

if [[ "$value" == "expected" ]]; then
  echo "Match"
fi

# Pattern matching
if [[ "$filename" == *.txt ]]; then
  echo "Text file"
fi
```

### Common Test Operators

```bash
# File tests
[[ -f "$file" ]]      # File exists
[[ -d "$dir" ]]       # Directory exists
[[ -r "$file" ]]      # Readable
[[ -w "$file" ]]      # Writable
[[ -x "$file" ]]      # Executable

# String tests
[[ -z "$string" ]]    # Empty string
[[ -n "$string" ]]    # Non-empty string
[[ "$a" == "$b" ]]    # Equal
[[ "$a" != "$b" ]]    # Not equal

# Numeric tests
[[ "$a" -eq "$b" ]]   # Equal
[[ "$a" -ne "$b" ]]   # Not equal
[[ "$a" -lt "$b" ]]   # Less than
[[ "$a" -gt "$b" ]]   # Greater than
```

### Short-Circuit Logic

```bash
# Execute command2 only if command1 succeeds
command1 && command2

# Execute command2 only if command1 fails
command1 || command2

# Multiple conditions
[[ -f "$file" ]] && [[ -r "$file" ]] && cat "$file"
```

## Functions

### Declaration

```bash
function_name() {
  local arg1="$1"
  local arg2="$2"

  # Function body
  echo "Processing: $arg1, $arg2"
  return 0
}

# Call function
function_name "value1" "value2"
```

### Return Values

```bash
check_status() {
  if [[ condition ]]; then
    return 0  # Success
  else
    return 1  # Failure
  fi
}

# Use return value
if check_status; then
  echo "Check passed"
else
  echo "Check failed"
fi
```

### Local Variables

Always use `local` for function variables:

```bash
process_data() {
  local input="$1"
  local temp_file="/tmp/temp_$$"

  # Process data
  # ...
}
```

## Command Substitution

Use `$()` instead of backticks:

```bash
# Good
current_date=$(date +%Y-%m-%d)
file_count=$(ls | wc -l)

# Avoid (backticks)
current_date=`date +%Y-%m-%d`
```

## Loops

### For Loops

```bash
# Iterate over list
for item in item1 item2 item3; do
  echo "$item"
done

# Iterate over files
for file in /path/*.txt; do
  [[ -f "$file" ]] && process "$file"
done

# C-style loop
for ((i = 0; i < 10; i++)); do
  echo "Iteration $i"
done
```

### While Loops

```bash
# Read file line by line
while IFS= read -r line; do
  echo "Line: $line"
done < input.txt

# Condition-based
count=0
while [[ $count -lt 10 ]]; do
  echo "$count"
  ((count++))
done
```

## Arrays

### Declaration and Access

```bash
# Declare array
declare -a services=("controller" "manager" "autocalibration")

# Access elements
echo "${services[0]}"      # First element
echo "${services[@]}"      # All elements
echo "${#services[@]}"     # Array length

# Iterate
for service in "${services[@]}"; do
  echo "Service: $service"
done
```

### Adding Elements

```bash
services+=("mapping")
```

## Error Handling

### Check Command Success

```bash
if command_that_might_fail; then
  echo "Success"
else
  echo "Failed with exit code: $?"
  exit 1
fi
```

### Error Messages to stderr

```bash
error_exit() {
  echo "Error: $1" >&2
  exit 1
}

# Usage
[[ -f "$config_file" ]] || error_exit "Config file not found: $config_file"
```

### Verbose Error Output

```bash
set -x  # Enable debug output (prints each command)
# Commands here will be echoed
set +x  # Disable debug output
```

## File Operations

### Reading Files

```bash
# Read entire file
content=$(cat file.txt)

# Read line by line
while IFS= read -r line; do
  echo "$line"
done < file.txt
```

### Writing Files

```bash
# Overwrite
echo "content" > file.txt

# Append
echo "more content" >> file.txt

# Here document
cat > config.txt << EOF
setting1=value1
setting2=value2
EOF
```

### Temporary Files

```bash
temp_file=$(mktemp)
trap "rm -f '$temp_file'" EXIT

# Use temp file
echo "data" > "$temp_file"
```

## Path Handling

### Absolute Paths

```bash
# Get script directory
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Construct absolute paths
config_file="$script_dir/config.txt"
```

### Path Components

```bash
filepath="/path/to/file.txt"

dirname=$(dirname "$filepath")    # /path/to
basename=$(basename "$filepath")  # file.txt
filename="${basename%.*}"         # file
extension="${basename##*.}"       # txt
```

## Process Management

### Background Jobs

```bash
# Start background job
long_running_command &
pid=$!

# Wait for specific job
wait $pid

# Wait for all background jobs
wait
```

### Process Substitution

```bash
# Compare outputs of two commands
diff <(command1) <(command2)

# Read from command output
while read -r line; do
  echo "$line"
done < <(command)
```

## SceneScape-Specific Patterns

### Docker Commands

```bash
# Build with progress
env BUILDKIT_PROGRESS=plain docker build \
  --build-arg VERSION="$VERSION" \
  -t "scenescape-service:$VERSION" \
  .
```

### Environment Variables

```bash
# Check required variables
: "${SUPASS:?SUPASS environment variable must be set}"
: "${DATABASE_PASSWORD:?DATABASE_PASSWORD must be set}"
```

### Makefile Integration

```bash
# Get variables from Makefile
VERSION=$(cat version.txt)
BUILD_DIR="${BUILD_DIR:-build}"
```

## Common Patterns

### Retry Logic

```bash
retry_command() {
  local max_attempts=3
  local attempt=1

  while [[ $attempt -le $max_attempts ]]; do
    if command_to_retry; then
      return 0
    fi
    echo "Attempt $attempt failed, retrying..." >&2
    ((attempt++))
    sleep 2
  done

  return 1
}
```

### Input Validation

```bash
validate_input() {
  local input="$1"

  if [[ -z "$input" ]]; then
    echo "Error: Input cannot be empty" >&2
    return 1
  fi

  if [[ ! "$input" =~ ^[0-9]+$ ]]; then
    echo "Error: Input must be numeric" >&2
    return 1
  fi

  return 0
}
```

### Logging

```bash
log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

log_error() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

log "Starting process"
log_error "Something went wrong"
```

## Anti-Patterns to Avoid

❌ **Don't use `eval`** (security risk):

```bash
# Bad
eval "$user_input"

# Good - use arrays or proper quoting
args=("$arg1" "$arg2")
command "${args[@]}"
```

❌ **Don't parse `ls` output**:

```bash
# Bad
files=$(ls *.txt)
for file in $files; do
  process "$file"
done

# Good
for file in *.txt; do
  [[ -f "$file" ]] && process "$file"
done
```

❌ **Don't use `cat` unnecessarily**:

```bash
# Bad (useless use of cat)
cat file.txt | grep pattern

# Good
grep pattern file.txt
```

❌ **Don't ignore errors**:

```bash
# Bad
command_that_might_fail

# Good
if ! command_that_might_fail; then
  echo "Command failed" >&2
  exit 1
fi
```

## Testing

### Manual Testing

Test scripts with:

```bash
bash -n script.sh   # Syntax check
shellcheck script.sh   # Linting
bash -x script.sh   # Debug mode
```

### Test Different Inputs

```bash
# Test edge cases
test_script() {
  ./script.sh ""           # Empty input
  ./script.sh "normal"     # Normal input
  ./script.sh "with spaces"  # Spaces
  ./script.sh "$long_string"  # Long input
}
```

## Documentation

### Script Header

```bash
#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#
# Script Name: deploy.sh
# Description: Deploy SceneScape services to production
# Usage: ./deploy.sh [environment]
#

set -euo pipefail
```

### Function Documentation

```bash
#
# Function: process_data
# Description: Process input data and generate output
# Arguments:
#   $1 - Input file path
#   $2 - Output directory
# Returns:
#   0 on success, 1 on error
#
process_data() {
  local input_file="$1"
  local output_dir="$2"
  # ...
}
```

## Performance

### Avoid Subshells

```bash
# Slower - creates subshell
count=$(expr $count + 1)

# Faster - built-in arithmetic
((count++))
```

### Use Built-ins

```bash
# Prefer bash built-ins over external commands
[[ "$string" == *pattern* ]]  # Built-in pattern matching
# vs
echo "$string" | grep pattern  # External process
```

## Portability

### Bash-specific Features

SceneScape uses bash, not POSIX sh. These are OK:

- `[[ ]]` tests
- Arrays
- `$()` command substitution
- `((  ))` arithmetic
- `[[  =~  ]]` regex matching

### Avoid Bashisms When Possible

But prefer portable constructs when they work equally well.
