# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL=/bin/bash
SECRETSDIR ?= ../../manager/secrets
MQTTUSERS ?= "controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"
AUTHFILES := $(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))

.PHONY: default authfiles django-secrets
default: authfiles django-secrets influxdb-secrets

%.auth:
	@set -e; \
	MQTTUSERS=$(MQTTUSERS); \
	for uid in $${MQTTUSERS}; do \
	    JSONFILE=$${uid%=*}; \
	    USERPASS=$${uid##*=}; \
	    case $${USERPASS} in \
	        *:* ) ;; \
	        * ) USERPASS=$${USERPASS}:$$(openssl rand -base64 12); \
	    esac; \
	    USER=$${USERPASS%:*}; \
	    PASS=$${USERPASS##*:}; \
	    if [ $(SECRETSDIR)/$${JSONFILE} = $@ ]; then \
	        echo '{"user": "'$${USER}'", "password": "'$${PASS}'"}' > $@; \
	        chmod 0644 $@; \
	    fi; \
	done

authfiles: $(SECRETSDIR) $(AUTHFILES)

django-secrets:
	@make -C ../../manager django-secrets SECRETSDIR=$(SECRETSDIR)

# Generate InfluxDB password and token
influxdb-secrets:
	@set -e; \
	mkdir -p $(SECRETSDIR)/influxdb2; \
	INFLUXDB_PASS=$$(openssl rand -base64 12); \
	INFLUXDB_TOKEN=$$(openssl rand -base64 32 | tr -d '/+' | tr -d '\n' | sed 's/.$$/==/'); \
	echo -n "admin" > $(SECRETSDIR)/influxdb2/influxdb2-admin-username; \
	echo -n "$$INFLUXDB_PASS" > $(SECRETSDIR)/influxdb2/influxdb2-admin-password; \
	echo -n "$$INFLUXDB_TOKEN" > $(SECRETSDIR)/influxdb2/influxdb2-admin-token;
