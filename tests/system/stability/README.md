# Stability system tests

These tests check if system runs correctly for 24 hours

## Description

### Stability

Starts SceneScape and monitors every 30 seconds for a duration of 24 hours.
The test monitors and tracks MQTT published messages, and tracks each of the sensors against each other and against the running average for that sensor.
The test will also try and log-in to the webserver every 30 seconds.
The test fails if the connection to the broker cannot be established, one of the sensors lags with respect to another, one of the sensors lags with respect to its running average, or if the log-in to the webpage fails.

## How to run

Note: The scripts will get the percebro user/password combination from percebro.auth.

Go to the scenescape directory, and execute the stability test:

```
jrmencha@nuc:~/github/git_latest2$ make SUPASS=admin123 -C tests system-stability
1005189e0adac4ec1f673b6cd10d1b066cad26f002ec7bb711142046af7d58b4
Creating gitlatest2_pgserver_1 ...
Creating gitlatest2_ntp_1 ...
Creating gitlatest2_broker_1 ...
Creating gitlatest2_pgserver_1
Creating gitlatest2_ntp_1
Creating gitlatest2_broker_1 ... done
Creating gitlatest2_video_1 ...
Creating gitlatest2_pgserver_1 ... done
Creating gitlatest2_scene_1 ...
Creating gitlatest2_web_1 ...
Creating gitlatest2_web_1
Creating gitlatest2_web_1 ... done
env USER=admin SUPASS=test_pass PERCUSER=cameras PERCPASS=Aiquoh6foo docker compose -f tests/system/stability/docker-compose-monitor.yml --project-directory /home/jrmencha/github/git_latest2  run test
Trying user admin password test_pass
Trying Percebro user cameras password Aiquoh6foo
Connected
First msg received (Topic scenescape/data/scene/1/apriltag)
00:00:00 : 8881 Objects detected in last 30 seconds (Min 742 Max 742)
Starting browser
Fetching page
Logged in: True
00:00:30 : 10016 Objects detected in last 30 seconds (Min 833 Max 834)
AVG model/stream fps: person:camera2 at 27.80 person:camera1 at 27.77 apriltag:camera2 at 27.77 apriltag:camera1 at 27.77
Starting browser
Fetching page
Logged in: True

...

Logged in: True
23:59:30 : 9603 Objects detected in last 30 seconds (Min 800 Max 800)
AVG model/stream fps: person:camera2 at 26.83 person:camera1 at 26.83 apriltag:camera2 at 26.82 apriltag:camera1 at 26.83
Starting browser
Fetching page
Logged in: True
Test passed! 24:00:00 of runtime
Stopping gitlatest2_video_1      ... done
Stopping gitlatest2_scene_1      ... done
Stopping gitlatest2_web_1    ... done
Stopping gitlatest2_broker_1 ... done
Stopping gitlatest2_ntp_1    ... done
Stopping gitlatest2_pgserver_1   ... done
Removing gitlatest2_video_1      ... done
Removing gitlatest2_scene_1      ... done
Removing gitlatest2_web_1    ... done
Removing gitlatest2_broker_1 ... done
Removing gitlatest2_ntp_1    ... done
Removing gitlatest2_pgserver_1   ... done
Network scenescape_test is external, skipping
scenescape_test
TV-017: Successful run for 24 hours: Test Passed


```
