# Positioning API v1

Versioned contracts for the PTZ capability of the Positioning service. For the full
contract reference, see
[docs/design/positioning-ptz-contracts.md](../../../../design/positioning-ptz-contracts.md).

| File                          | Contents                                                        |
| ----------------------------- | --------------------------------------------------------------- |
| `ptz.proto`                   | `PTZSample` raw-ingest messages and the `PTZPoseIngest` service |
| `ptz_calibration.schema.json` | `ptz_calibration` data contract (parameterization `v1`)         |
| `generate.sh`                 | Regenerates the committed Python stubs                          |

## Package and Import Path

The protobuf package is `scenescape.ptz.v1`. The Python import path is
`positioning.v1` (for example, `from positioning.v1 import ptz_pb2`). The import path
comes from the file location relative to the `-I docs/user-guide/api-docs` include root, not from the
`package` statement. The two names are different on purpose.

## Compatibility Policy

The `scenescape.ptz.v1` package is the wire compatibility boundary.

- Within v1, you can only add new optional fields.
- Never renumber, rename, retype, or reuse a field, and never change what an existing
  field means. Mark removed fields as `reserved`.
- Any incompatible change requires a new package, for example `scenescape.ptz.v2`.

In v1, the ONVIF poller passes `PTZSample` to the Resolver in-process. The
`PTZPoseIngest` service is kept for a future authenticated external producer.

## Regenerating Stubs

```bash
pip install grpcio-tools==1.71.2   # protobuf 5.29.x, as pinned in tests/requirements.txt
docs/user-guide/api-docs/positioning/v1/generate.sh  # set PYTHON=<interpreter> to override python3
```

The script writes `ptz_pb2.py`, `ptz_pb2.pyi`, and `ptz_pb2_grpc.py` to
`positioning/src/positioning/v1/`. It adds SPDX headers and lint-skip directives, and
reindents the Python files to the repository's 2-space style. Running it again
produces identical output.
