#!/bin/sh

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

DISTRO=$(lsb_release -is | tr "[:upper:]" "[:lower:]")
CODENAME=$(lsb_release -cs)

sudo apt-get update
if [ $? != 0 ] ; then
    echo update failed
    exit 1
fi

sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg2 \
    software-properties-common
if [ $? != 0 ] ; then
    echo install failed
    exit 1
fi

if [ ! -d "/etc/apt/keyrings" ] ; then
    sudo install -m 0755 -d /etc/apt/keyrings
    if [ $? != 0 ] ; then
        echo install command failed
        exit 1
    fi
else
    echo "/etc/apt/keyrings directory already exists"
fi

sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
if [ $? != 0 ] ; then
    echo key add failed
    exit 1
fi

sudo chmod a+r /etc/apt/keyrings/docker.asc
if [ $? != 0 ] ; then
    echo chmod command failed
    exit 1
fi

echo \
  "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${DISTRO} \
  ${CODENAME} stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
if [ $? != 0 ] ; then
    echo add repo failed
    exit 1
fi

sudo apt-get update
if [ $? != 0 ] ; then
    echo update failed
    exit 1
fi

sudo apt-get install docker-ce -y
if [ $? != 0 ] ; then
    echo docker install failed
    exit 1
fi

sudo apt-get install docker-compose-plugin -y
if [ $? != 0 ] ; then
    echo docker compose install failed
    exit 1
fi

sudo usermod -a -G docker ${USER}
if [ $? != 0 ] ; then
    echo add user to docker group failed
    exit 1
fi
egrep -q '^docker:.*'${USER} /etc/group
if [ $? != 0 ] ; then
    echo add user to docker group failed
    exit 1
fi

# If docker-bridge file exists it was probably setup for Intel proxies, make containers use host DNS
if [ -e /etc/NetworkManager/dnsmasq.d/docker-bridge.conf ] ; then
    sudo sh -c "echo 'listen-address=172.17.0.1' >> /etc/NetworkManager/dnsmasq.d/docker-bridge.conf"
    sudo systemctl restart NetworkManager
fi

if ! groups | grep -qw docker ; then
    echo
    echo "####################"
    echo
    echo You need to log out and back in so that your
    echo user will be part of the docker group.
    echo
    echo "####################"
    echo
fi
