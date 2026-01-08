# Steps to deploy SceneScape for IGK6 demo room

1. Deploy Docker: `make; make demo` (custom demo configuration files are loaded automatically)
2. Remove OOB demo scenes.
3. Import scene from: repos/scenescape/demo_scene/IGK6-demo-room.zip

Work-arounds needed:
- GLB file not positioned correctly after scene import. Work-around: use REST API to update scene translation and location as in scene Json file.
- After docker compose restart, GLB file is lost and needs to be loaded manually.
