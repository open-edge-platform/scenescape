# PX4 SIH Drone → SceneScape Demo

Simulate a quadcopter with [PX4 SIH](https://docs.px4.io/main/en/sim_sih/) (Simulation-In-Hardware), bridge its **MAVLink** telemetry into SceneScape with the existing [`mavlink_to_external_source.py`](../external_source_adapters/mavlink_to_external_source.py) adapter, and verify **spatial analytics** when the drone enters a geospatial **Region of Interest (ROI)**.

SIH runs physics inside PX4 via uORB — no external simulator. PX4 still exposes standard MAVLink (`GLOBAL_POSITION_INT`, `ATTITUDE`) on UDP, which is what the SceneScape adapter consumes.

## Architecture

```text
PX4 SIH (Docker)          MAVLink adapter              Scene Controller
  uORB physics    -->  UDP 14550  -->  pymavlink  -->  MQTT external/
  simulated GPS              mavlink_to_external_source.py   wgs84 pose
                                                                    |
                                                                    v
                                                          geospatial scene + ROI
                                                                    |
                                                                    v
                                              MQTT scenescape/event/region/.../count
```

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| SceneScape | `make demo` with `MAPBOX_API_KEY` and `SUPASS` |
| Docker | For `px4io/px4-sitl-sih` (no PX4 toolchain needed) |
| Python 3.10+ | `pip install -r tools/external_source_adapters/requirements.txt` |
| Mapbox token | `MAPBOX_API_KEY` — [configure keys](../../docs/user-guide/how-to-guides/build-a-scene/configure-geospatial-map-service-api-keys.md) |

## Quick start

### 1. Start SceneScape

```bash
cd /path/to/scenescape
export MAPBOX_API_KEY="pk...."   # your Mapbox public token
export SUPASS="your-admin-password"
make demo DEMO_REBUILD_IMAGES=false
```

Log in at `https://localhost/` as `admin` / `$SUPASS`.

### 2. Create geospatial scene + ROI

```bash
export MAPBOX_API_KEY="pk...."
export SUPASS="..."
./tools/px4_sih_demo/run_demo.sh setup
```

This geocodes a location (default: **Shoreline Amphitheatre, Mountain View, CA**), downloads a Mapbox satellite snapshot, creates a geo-calibrated scene, adds a centred ROI, and writes `px4_sih_config.json` with matching `PX4_HOME_*` coordinates.

Override the map area:

```bash
export PX4_DEMO_LOCATION="37.3869,-121.9641"   # lat,lon
export PX4_DEMO_MAP_ZOOM=19
./tools/px4_sih_demo/run_demo.sh setup
```

### 3. Start PX4 SIH

```bash
./tools/px4_sih_demo/run_demo.sh start
```

Uses [`px4io/px4-sitl-sih`](https://hub.docker.com/r/px4io/px4-sitl-sih) with `PX4_HOME_LAT/LON/ALT` from the config so simulated GPS matches the SceneScape map.

### 4. Run the MAVLink adapter (new terminal)

```bash
./tools/px4_sih_demo/run_demo.sh adapter
```

Publishes to `scenescape/external/px4-sih-drone-1/vehicle` with `reference_frame: wgs84`. The controller auto-binds wgs84 poses to the geo-calibrated scene.

**The adapter only publishes GPS — it does not fly the drone.**

### 5. Fly through the ROI (third terminal — required for movement & analytics)

```bash
./tools/px4_sih_demo/run_demo.sh fly
```

Arms the drone, takes off, moves **outside** the centred ROI, then ping-pongs across the **north edge** every ~4 seconds so spatial analytics fires enter/exit count events. Press Ctrl+C to stop.

Tune timing or edge:

```bash
./tools/px4_sih_demo/run_demo.sh fly --leg-period 3 --axis east
```

Legacy one-shot square mission: `./tools/px4_sih_demo/run_demo.sh fly --pattern square`

### 6. Watch spatial analytics

```bash
./tools/px4_sih_demo/run_demo.sh watch-roi
```

You should see ROI **enter/exit count** events when the drone crosses the region. Also open the scene in the SceneScape UI — the vehicle appears on the satellite map.

### Stop

```bash
./tools/px4_sih_demo/run_demo.sh stop
```

## How SIH maps to the MAVLink adapter

| SIH / PX4 | MAVLink message | SceneScape field |
|-----------|-----------------|------------------|
| Simulated GPS (from `PX4_HOME_*` + dynamics) | `GLOBAL_POSITION_INT` | `pose.lat_long_alt` (wgs84) |
| Attitude estimator | `ATTITUDE` | `pose.rotation`, `objects[].rotation` |
| Vehicle identity | — | `source_id` = `SCENESCAPE_SOURCE_ID` (persistent) |

The adapter does **not** read uORB directly; PX4's MAVLink module translates internal state to MAVLink automatically in SITL/SIH mode.

Default MAVLink ports (single instance):

| Port | Direction | Consumer |
|------|-----------|----------|
| 14550/udp | PX4 → GCS / adapter | `udpin:0.0.0.0:14550` (PX4 container uses `--network host`) |
| 14540/udp | PX4 ↔ offboard | `fly_roi_pattern.py` mission upload |

## Manual PX4 build (optional)

If you prefer a local PX4 tree instead of Docker:

```bash
export PX4_HOME_LAT=37.3869
export PX4_HOME_LON=-121.9641
export PX4_HOME_ALT=15
make px4_sitl_sih sihsim_quadx
```

Then point `MAVLINK_CONNECTION=udp:127.0.0.1:14550` at the adapter.

## Contract references

- External source MQTT contract: [`data_formats.md`](../../docs/user-guide/microservices/controller/data_formats.md)
- Adapter how-to: [`publish-external-source-adapter.md`](../../docs/user-guide/how-to-guides/publish-external-source-adapter.md)
- Spatial analytics: [`configure-spatial-analytics.md`](../../docs/user-guide/how-to-guides/build-a-scene/configure-spatial-analytics.md)

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Adapter logs "Published" but nothing in UI | Open scene **PX4 SIH Drone Demo** (not Queuing/Retail). Ensure MQTT shows **connected** in the scene UI (Connect button). Run `./run_demo.sh adapter` — it applies host compose overrides and restarts the adapter with a valid object `size` (required for the analytics → UI path). |
| Controller `FELL BEHIND` / `SKIPPING` | Host clock differs from container NTP. The demo compose override enables `--rewriteBadTime --maxlag 10` on the scene controller; re-run `./run_demo.sh adapter` to apply it. |
| Controller `NotImplementedError` (non-tracker mode) | Scene must have `use_tracker: true`. Re-run `./run_demo.sh setup` or set it in the scene UI / REST API. |
| No object on map | Scene has `output_lla: true` and valid `map_corners_lla`; adapter logs show LLA publishes |
| Pose rejected | Drone LLA must fall inside the scene's four corners |
| PX4 won't arm | `docker logs px4-sih-demo`; wait for GPS fix in SIH (~5 s) |
| Drone stuck / no ROI events | Adapter does **not** fly the drone — run `./run_demo.sh fly` in another terminal. If PX4 entered RTL, `fly` auto-restarts the mission; or `./run_demo.sh stop && ./run_demo.sh start` then re-run adapter + fly. |
| Mapbox errors on setup | Token scopes + `MAPBOX_API_KEY` passed to manager container |
