#!/bin/bash

set -e

if [ -e docker-compose.yml ]; then
    while true; do
        read -p "docker-compose.yml already exists. Replace it with a new one? [y/n] " yn
        case $yn in
            [Yy]*)
                break
                ;;
            [Nn]*)
                # Optionally validate here if you have a validator
                echo "Keeping existing docker-compose.yml"
                exit 0
                ;;
            *)
                echo "Please answer yes or no."
                ;;
        esac
    done
fi

rm -f docker-compose.yml
make -C docker ../docker-compose.yml