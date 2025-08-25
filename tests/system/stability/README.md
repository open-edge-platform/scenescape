# Stability system tests

These tests check if system runs correctly for 24 hours

## Description

### Stability

Starts SceneScape and monitors every 30 seconds for a duration of 24 hours.
The test monitors and tracks MQTT published messages, and tracks each of the sensors against each other and against the running average for that sensor.
The test will also try and log-in to the webserver every 30 seconds.
The test fails if the connection to the broker cannot be established, one of the sensors lags with respect to another, one of the sensors lags with respect to its running average, or if the log-in to the webpage fails.

## How to run

Note: The scripts will get the user/password combination from controller.auth.

Go to the scenescape directory, and execute the stability test:

```bash
make SUPASS=admin123 -C tests system-stability
```
