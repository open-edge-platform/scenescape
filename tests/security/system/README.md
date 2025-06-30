# Security system tests

These tests check if SceneScape rejects invalid certificate / authentication

## Description

### CT198a: Implementation does not default to insecure legacy protocols (bad auth)

The test will try to connect to the MQTT broker with invalid user/password combination.

### CT198b: Implementation does not default to insecure legacy protocols (insecure)

The test will try to connect to the MQTT broker with the right user/password combination, but requesting an insecure connection.

## How to run

Call the script from the parent (root) SceneScape directory.

CT198a: bad auth

Run the test_negative_mqtt.insecure_auth.sh test.

```
jrmencha@nuc:~/github/git_latest2$ tests/security/system/test_negative_mqtt_insecure_auth.sh
4addedde161c614573ec44f3e95e9afbc2bbf7e649aeda00e0cde75727be0c04
Creating gitlatest2_pgserver_1 ...
Creating gitlatest2_broker_1 ...
Creating gitlatest2_ntp_1 ...
Creating gitlatest2_pgserver_1
Creating gitlatest2_ntp_1
Creating gitlatest2_pgserver_1 ... done
Creating gitlatest2_web_1 ...
Creating gitlatest2_broker_1 ... done
Creating gitlatest2_scene_1 ...
Creating gitlatest2_video_1 ...
Creating gitlatest2_scene_1
Creating gitlatest2_video_1 ... done
TIMEZONE IS
Using user tmp pass dummy but insecure option
Connected
Connected
Connected
Connected
0 Objects detected in 10 seconds
Test passed!
Stopping gitlatest2_scene_1      ... done
Stopping gitlatest2_video_1      ... done
Stopping gitlatest2_web_1    ... done
Stopping gitlatest2_pgserver_1   ... done
Stopping gitlatest2_broker_1 ... done
Stopping gitlatest2_ntp_1    ... done
Removing gitlatest2_scene_1      ... done
Removing gitlatest2_video_1      ... done
Removing gitlatest2_web_1    ... done
Removing gitlatest2_pgserver_1   ... done
Removing gitlatest2_broker_1 ... done
Removing gitlatest2_ntp_1    ... done
Network scenescape_test is external, skipping
scenescape_test
CT198a: Implementation does not default to insecure legacy protocols (bad auth): Test Passed

```

CT198b: insecure connection

Run the test_negative_mqtt.insecure_cert.sh test.

NOTE: The test will output the user/password combination it used during the test.
The tester _should_ verify these are the right credentials (vs secrets/auth/percebro.auth) to ensure
that the system refused connection due to the request for an insecure connection.

```
jrmencha@nuc:~/github/secrets_wip/git_latest2$ tests/security/system/test_negative_mqtt_insecure_cert.sh
07fff57cc9424990e25a750c283048464196df1c33a11d7c315b1c01c4b71217
Creating gitlatest2_pgserver_1 ...
Creating gitlatest2_broker_1 ...
Creating gitlatest2_ntp_1 ...
Creating gitlatest2_ntp_1
Creating gitlatest2_pgserver_1
Creating gitlatest2_pgserver_1 ... done
Creating gitlatest2_video_1 ...
Creating gitlatest2_web_1 ...
Creating gitlatest2_scene_1 ...
Creating gitlatest2_video_1
Creating gitlatest2_scene_1
Creating gitlatest2_web_1 ... done
TIMEZONE IS
Note: Tester should verify Manually that user cameras pw 6t3Z6HUeicZShfqP are the right secrets!
Test passed! Bad certificate, unable to connect!
Stopping gitlatest2_web_1    ... done
Stopping gitlatest2_scene_1      ... done
Stopping gitlatest2_video_1      ... done
Stopping gitlatest2_pgserver_1   ... done
Stopping gitlatest2_broker_1 ... done
Stopping gitlatest2_ntp_1    ... done
Removing gitlatest2_web_1    ... done
Removing gitlatest2_scene_1      ... done
Removing gitlatest2_video_1      ... done
Removing gitlatest2_pgserver_1   ... done
Removing gitlatest2_broker_1 ... done
Removing gitlatest2_ntp_1    ... done
Network scenescape_test is external, skipping
scenescape_test
CT198b: Implementation does not default to insecure legacy protocols (bad cert): Test Passed
```
