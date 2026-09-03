# Autocalibration Tools

## Perceptual Sensor CLI

Command-line tool for manipulating point clouds and interfacing with the perceptual-sensor API in the Autocalibration service.

Path: `autocalibration/tools/perceptual_sensor_cli.py`

Usage (run the commands in the repository root folder):

```bash
make && make demo
cd autocalibration/tools/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python perceptual_sensor_cli.py --help
```

### Localization Example

1. Deploy a scene and load the scene's 3D model as GLB or PLY mesh.

2. Convert the scene model from GLB to PCD with the `glb-to-cloud` command: `python perceptual_sensor_cli.py glb-to-cloud --number-of-points 1500000 <scene mesh>.glb scene.pcd`.

3. Transform the scene point cloud into a lidar input PCD with the `transform` command: `python perceptual_sensor_cli.py transform --matrix transform.json lidar_input.pcd scene.pcd`
   Example transform matrix:
   ```json
   [
     [0.76604444, 0.0, -0.64278761, 0.39654395],
     [0.21984631, 0.93969262, 0.26179939, -5.92355389],
     [0.60365239, -0.34202014, 0.71984631, -2.65674301],
     [0.0, 0.0, 0.0, 1.0]
   ]
   ```

4. Run localization:
```bash
python perceptual_sensor_cli.py localize --sensor-id 0 --scene-id <scene UUID> --pointcloud lidar_input.pcd --auth ../../manager/secrets/calibration.auth
```

5. Check result:
```bash
python perceptual_sensor_cli.py status --sensor-id 0 --auth ../../manager/secrets/calibration.auth
```

The resulting transform should be the inverse of the initial transform (some negligible estimation errors are expected):
```json
[
  [ 0.76618714, -0.00021979, -0.64261755,  0.39657731],
  [ 0.21990722,  0.93971482,  0.26207522, -5.92461416],
  [ 0.60419012, -0.34195917,  0.72004574, -1.65872163],
  [ 0.0,         0.0,         0.0,         1.0]
]
```
