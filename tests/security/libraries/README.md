# Security library version tests

These tests gather and check the installed versions of packages in the image.

## Description

### Get image versions

This test uses dpkg to check the version installed for each of the packages in the system.
This test needs to be run within the sscape image.

### Get latest versions

This script checks the latest available package in the Ubuntu repositories (for 20.04) for each of the packages obtained from the previous step.
This test needs to be run outside of the sscape image.

## How to run

Instantiate the scenescape image, to run shell. Check that the network is the same as the one created for the docker-compose instance.

```
docker run  --hostname test1 -v  `pwd`:/workspace -v /var/tmp:/var/tmp  -v /dev/shm:/dev/shm  --privileged  -it scenescape
```

Then run the get image versions:

```
scenescape@test1:/workspace$ cd tests/security/libraries/

scenescape@test1:/workspace$ ./test_get_image_versions.sh /workspace/all_packages.txt

```

Then, after exiting the docker image:
```
jrmencha@nuc:~/scenescape_rc1$ tests/security/libraries/test_get_latest_versions.sh all_packages.txt | tee all_packages_check.txt
IMAGE has pkg adduser w/ version :3.118ubuntu2:
VERSION 3.118ubuntu2 matches latest available.

IMAGE has pkg adwaita-icon-theme w/ version :3.36.1-2ubuntu0.20.04.2:
VERSION 3.36.1-2ubuntu0.20.04.2 matches latest available.


IMAGE has pkg apache2 w/ version :2.4.41-4ubuntu3.4:
VERSION 2.4.41-4ubuntu3.4 matches latest available.


IMAGE has pkg apache2-bin w/ version :2.4.41-4ubuntu3.4:
VERSION 2.4.41-4ubuntu3.4 matches latest available.
...
```


When there is a mismatch, the output will show:
```
IMAGE has pkg apt w/ version :2.0.4:
Version mismatch?
BINARY :apt, libapt-pkg6.0, apt-doc, libapt-pkg-dev, libapt-pkg-doc, apt-utils, apt-transport-https:
VERSION :2.0.6:
apt has 2.0.4 and latest is 2.0.6 (covers apt, libapt-pkg6.0, apt-doc, libapt-pkg-dev, libapt-pkg-doc, apt-utils, apt-transport-https)
```

It is left to the user to verify the output of the script, since this only performs a basic string matching check.
