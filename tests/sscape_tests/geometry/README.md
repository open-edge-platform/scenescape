# Steps to Run

From the repo root:

```bash
make setup-pytest
tests/.venv/bin/pytest tests/sscape_tests/geometry/ -v
```

# Expected Results

All tests should pass. In the JUnit XML they are reported under the test name "NEX-T10454".
