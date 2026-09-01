# Steps to deploy SceneScape for IGK6 demo room

1. In a clean and up-to-date SceneScape repository folder check out `demo-room-igk6` branch.
2. Deploy Docker: `export SUPASS=<your password>; make; make demo-room` (custom demo configuration files are loaded automatically).

`make demo-room` runs [`sample_data/deploy-demo.sh`](sample_data/deploy-demo.sh) automatically once the containers are up. The script waits for the REST API, removes the out-of-box demo scenes and cameras, and imports the scene from [`sample_data/demo_scene/IGK6-demo-room.zip`](sample_data/demo_scene/IGK6-demo-room.zip).

To run the full deployment (branch checkout, build, and demo configuration) with a single command:

```
export SUPASS=<your password>
./sample_data/deploy-demo.sh
```

Now you are ready experiment and watch demo scene on UI and statistics on Grafana (http://<host IP>:3000, credentials: admin/admin).

## Troubleshooting

If Grafana dashboard shows authentication problem with InfluxDB datasource, restart business logic with volume clean-up to start it with fresh credentials:

```
docker compose -f docker-compose-bussiness-logic.yml down --volumes
docker compose -f docker-compose-bussiness-logic.yml up -d
```
