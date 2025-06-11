# How to improve performance

## OpenCV Cores
To improve video processing performance, percebro has the ability to multithread the video input. With the number of cvcores set, OpenCV will set the number
of threads for the next parallel region.

Here is an example of using cvcores:

    $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain pv0078 --cvcores 1

## OpenVINO™ Cores
Percebro performs asynchronous requests with OpenVINO™. This means the service can send inference requests without having to wait for previous
requests to complete. This essentially allows Percebro to perform other tasking which improves performance. The ovcores option
is mostly used to request the number of threads to be used for inferencing.

Here is an example of using ovcores:

    $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain pv0078 --ovcores 2

## GPU Decoding

Note: As a dependency, the host system should have the proper kernel + drivers to detect and use the desired GPU.

If the system has an integrated graphics card, or a discrete graphics card, it should be detected during build.
This will enable percebro to use the available graphics card during decoding when specifying the `--cv_subsystem GPU` option in the command line.

When the `--cv_subsystem` is not provided, percebro will default to use the CPU for decoding. The following command is equivalent:

      $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain retail --cv_subsystem CPU

In order to ask Percebro to use GPU X (enumeration starts at 0) for decoding, specify `GPU.X`:

      $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain retail --cv_subsystem GPU.1

Note: Each percebro container instance will be tied to one GPU; it is not possible to use GPU.0 for one input and GPU.1 for another in the same command. It is however possible to have concurrent Percebro instances running using different GPUs each.

Note: It is possible to have both GPU decoding and GPU inferencing running on the same, or different GPUs:

Using GPU.0 for inferencing, and GPU.1 for decoding:

      $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain retail=GPU.0 --cv_subsystem GPU.1

Using GPU.1 for inferencing, and GPU.0 for decoding:

      $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain retail=GPU.1 --cv_subsystem GPU.0

Using GPU.1 for both inferencing and decoding:

      $ docker/scenescape-start percebro localhost --camera path/to/video.mp4 --camerachain retail=GPU.1 --cv_subsystem GPU.1

Monitoring of the GPU can be done using the 'intel_gpu_top' command (part of package intel-gpu-tools), which needs root access:

      $ sudo intel_gpu_top

For multiple GPU systems, the device to monitor may need to be specified:
      $ sudo intel_gpu_top -d drm:/dev/dri/card0

      or

      $ sudo intel_gpu_top -d drm:/dev/dri/card1

## Images

For performance testing purposes it is useful to process a given image many times to determine statistics like inferencing latency and throughput. For example, to process an image 1000 times and log the results without publishing to MQTT, try the following example command:

        $ docker/scenescape-start --image scenescape-percebro:latest --shell
        usermod: no changes
        TIMEZONE IS /usr/share/zoneinfo/Etc/UTC
        scenescape@hostname:/home/user/SceneScape$ percebro/percebro --camera path/to/image.jpg \
                --camerachain pv0078 --debug --stats --frames 1000 >> log.txt

See [below](#heterogeneous-performance-testing) for how to target inferencing on various available hardware.

## Heterogenous Inferencing

Depending on use case and available hardware, it may be very beneficial to run inferencing on different target hardware for each model. If the system is equipped with an HDDL card and a GPU, the following command will target the `retail` model to the GPU and the `reid` model to the HDDL card:

        $ docker/scenescape-start percebro 0 192.168.1.23 --camerachain retail=GPU+reid=HDDL

The `=` sign is used to assign a given inferencing operation to the target hardware, and Percebro respects that assignment inside the entire model inferencing chain. To use the above vehicle and person inferencing chain:

        $ docker/scenescape-start percebro 0 192.168.1.23 --camerachain v0002=CPU+[vattrib=HDDL,lpr=HDDL],retail=GPU+[reid=CPU,head=HDDL+agr=GPU]

## Heterogeneous Performance Testing

It is recommended to use static images for performance testing and optimization. Using the above image example, test inferencing performance on various hardware targets quickly and easily:


        $ docker/scenescape-start --image scenescape-percebro:latest --shell
        usermod: no changes
        TIMEZONE IS /usr/share/zoneinfo/Etc/UTC
        scenescape@hostname:/home/user/SceneScape$ percebro/percebro --camera path/to/image.jpg \
        --camerachain retail=CPU+reid=HDDL --debug --stats --frames 1000 >> log.txt

Or:

        scenescape@hostname:/home/user/SceneScape$ percebro/percebro --camera path/to/image.jpg \
        --camerachain retail=GPU+reid=CPU --debug --stats --frames 1000 >> log.txt
