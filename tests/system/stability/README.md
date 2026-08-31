# Stability system tests

These tests check if system runs correctly for 24 hours

## Description

### Stability

Starts Scenescape and monitors every 30 seconds for a duration of 24 hours.
The test monitors and tracks MQTT published messages, and tracks each of the sensors against each other and against the running average for that sensor.
The test will also try and log-in to the webserver every 30 seconds.
The test also samples system memory usage every cycle and checks for sustained growth across the run.
Memory sampling only starts after a 20 minute settle period so that container start-up (model download, cache warm-up) is not counted as growth.
The test fails if the connection to the broker cannot be established, one of the sensors lags with respect to another, one of the sensors lags with respect to its running average, or if the log-in to the webpage fails.
It also fails when the moving-average memory trend indicates potential leak-like behavior, that is the end average exceeds the start average by at least 10% relative and 10 percentage points of host memory, for 3 consecutive windows.

## How to run

Note: The scripts will get the user/password combination from controller.auth.

Go to Scenescape directory, and execute the stability test:

```bash
make SUPASS=admin123 -C tests system-stability
```
