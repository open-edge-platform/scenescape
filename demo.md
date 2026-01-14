# Steps to deploy SceneScape for IGK6 demo room

1. In a clean and up-to-date SceneScape repository folder check out `demo-room-igk6` branch.
2. Deploy Docker: `export SUPASS=<your password>; make; make demo-room` (custom demo configuration files are loaded automatically).
3. Remove OOB demo scenes and cameras.
4. Import scene from: `demo_scene/IGK6-demo-room.zip`.

Now you are ready experiment and watch demo scene on UI and statistics on Grafana (http://<host IP>:3000, credentials: admin/admin).

## Work-arounds needed:

- After scene import step GLB file not positioned correctly. Work-around: use REST API to update scene mesh translation and rotation as in scene Json file (it is stored as a part of `demo_scene/IGK6-demo-room.zip` archive), then refresh UI page. Bug: **ITEP-83513**
  
  Example:

  ```
  export TOKEN=$(curl --location --insecure -X POST -d "username=admin&password=$SUPASS" https://localhost/api/v1/auth | jq .token | tr -d '"' )
  curl --location --insecure -X POST -H "Content-Type: application/json" -H "Authorization: Token $TOKEN" "https://localhost/api/v1/scene/901cbfb1-31e0-4a4a-b759-f2607b2d4f37" -d '{"mesh_translation":[3.0546417236328125,2.7034544944763184,1.5706065893173218],"mesh_rotation":[90,0,0]}'
  ```

  Update the numbers from above command with values from scene JSON file, if needed.

- After docker compose restart, GLB file is lost and needs to be loaded manually (it is stored as a part of `demo_scene/IGK6-demo-room.zip` archive). Bug: **ITEP-83950**

## Troubleshooting

If Grafana dashboard shows authentication problem with InfluxDB datasource, restart business logic with volume clean-up to start it with fresh credentials:

```
docker compose -f docker-compose-bussiness-logic.yml down --volumes
docker compose -f docker-compose-bussiness-logic.yml up -d
```
