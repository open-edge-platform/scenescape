# Robot Vision

Algorithms for sensor fusion, environment perception, object detection and tracking in C++ with Python interface

[![Build](https://github.com/intel-innersource/applications.robotics.mobile.robot-vision/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/intel-innersource/applications.robotics.mobile.robot-vision/actions/workflows/ci.yml)

# Build Dependencies

```bash
sudo apt install build-essential pkg-config python3 python3-setuptools python3-wheel cmake python3-dev googletest libpython3-dev
```

# Install Dependencies

```bash
sudo apt install pybind11-dev libopencv-dev libeigen3-dev libpcl-dev libtbb-dev libomp-dev libgoogle-glog-dev libgflags-dev libatlas-base-dev libsuitesparse-dev
```

# Installation

```bash
python3 setup.py bdist_wheel
pip3 install dist/robot_vision-X.X.X-cpXX-cpXXm-linux_x86_64.whl
```

## Documentation

### Html documentation

Install necessary packages

```bash
pip3 install sphinx, sphinx-rtd-theme
```

then build the documentation with:

```bash
make docshtml
```

after that you can launch the doc server with

```bash
make docserve
```

To access the remote server from your windows machine, activate the port forwarding via ssh

```bash
ssh -N -f -L localhost:8000:localhost:8000 userid@machine
```

Access the documentation at http://localhost:8000

### PDF documentation

Install latexmk

```bash
sudo apt install latexmk
```

Call the make command

```bash
make docspdf
```

The pdf will be generated in docs/\_build/latex/robot_vision.pdf
