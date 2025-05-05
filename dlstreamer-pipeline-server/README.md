# Steps to integrate Intel® Deep Learning Streamer Pipeline Server into SceneScape
* Edit ```docker-compose.yml``` to enable DL Streamer Pipeline Server and disable the respective percebro section
* Create a .env file in same directory as docker-compose.yml.
* Get UID,GID of current user by following commands
```
id -u
```
and,
```
id -g
```
* Set UID and GID as follows in the .env file
```
UID=<uid obtained from previous step>
GID=<gid obtained from previous step>
```
* Ensure OMZ models(person-detection-retail-0013 and person-reidentification-retail-0277) are available in <scenescape_dir>/models/intel/
* From <scenescape_dir>, run ```dlstreamer-pipeline-server/convert_mp4_to_ts.sh``` to convert mp4 files in <scenscape_dir>/sample_data directory to ts files

# Additional notes
* If you encounter error message
>Error response from daemon: Get "https://amr-registry.caas.intel.com/v2/": tls: failed to verify certificate: x509: certificate signed by unknown authority

from docker daemon, refer to [wiki article](https://wiki.ith.intel.com/display/SceneScape/How+to+setup+computing+systems+to+pull+docker+images+from+Intel+harbor+registry) and employ one of the solutions listed.
* To run a video file in a infinite loop using gstreamer multifilesrc element, convert the input mp4 into mpeg-ts format. (ffmpeg -i <infile.mp4> -c copy <outfile.ts>).
* DL Streamer Pipeline Server container on startup runs the pipelines instantiated by ```<scenescape_dir>/dlstreamer-pipeline-server/config.json``` which has the type of pipeline to run and pipeline parameters(video file/camera, ntp server name, camera id, fov, etc)
* Pipeline definitions are defined in ```<scenescape_dir>/dlstreamer-pipeline-server/pipelines/user_defined_pipelines/```. Create a subdirectory for each type.
