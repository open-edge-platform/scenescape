# Steps to Run

- make -C tests geometry-unit

Or manually (run from repo root):

```bash
docker run --rm --privileged --cap-add=SYS_ADMIN --cap-add=SYS_PTRACE \
    --workdir=/workspace \
    --user $(id -u) --userns=host \
    --volume="${PWD}:/workspace:rw" \
    --volume="${PWD}/manager/secrets:/run/secrets:ro" \
    -e PYTHONPATH=/workspace \
    scenescape-manager-test:latest \
    pytest tests/sscape_tests/geometry/
```

# Expected Results

All tests should pass and should show an output: "NEX-T10454: PASS"
