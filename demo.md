# Steps to deploy SceneScape for IGK6 demo room

1. Deploy Docker: `export SUPASS=<your password>; make; make demo` (custom demo configuration files are loaded automatically)
2. Remove OOB demo scenes.
3. Import scene from: repos/scenescape/demo_scene/IGK6-demo-room.zip
4. Deploy business logic: `docker compose -f docker-compose-bussiness-logic.yml up -d`
5. Watch demo scene on UI and statistics on Grafana (http://<host IP>:3000, credentials: admin/admin)

Work-arounds needed:
- GLB file not positioned correctly after scene import. Work-around: use REST API to update scene translation and location as in scene Json file.
- After docker compose restart, GLB file is lost and needs to be loaded manually.
