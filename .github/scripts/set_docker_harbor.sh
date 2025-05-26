#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -E -o pipefail
shopt -s extdebug

NC="\033[0m"
GREEN="\e[32m"

sudo apt-get -y install unzip gnome-keyring

echo -e "${GREEN}\nAdd Intel cerfiticates for Intel Harbor${NC}"
wget --directory-prefix=/tmp http://certificates.intel.com/repository/certificates/IntelSHA2RootChain-Base64.zip
sudo unzip -o /tmp/IntelSHA2RootChain-Base64.zip -d /usr/local/share/ca-certificates/
rm /tmp/IntelSHA2RootChain-Base64.zip
sudo update-ca-certificates

echo -e "${GREEN}\nRestart docker services${NC}"
sudo systemctl -q daemon-reload
sudo systemctl -q restart docker

# Attempting to connect to Intel Harbor
echo -e "\n${GREEN}Docker credential for Intel Harbor: (UNIX username/password)${NC}"
docker login amr-registry-pre.caas.intel.com
