# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ROOT_DIR := $(abspath ../..)
VERSION := $(shell cat $(ROOT_DIR)/version.txt)

default: up

.PHONY: up
up:
	VERSION=$(VERSION) docker compose -f compose.app.yml up --build -d

.PHONY: down
down:
	VERSION=$(VERSION) docker compose -f compose.app.yml down
