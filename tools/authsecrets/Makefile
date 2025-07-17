# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

SHELL=/bin/bash
SECRETSDIR ?= ../../manager/secrets
MQTTUSERS ?= "percebro.auth=cameras controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"
AUTHFILES := $(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))

.PHONY: default authfiles django-secrets
default: authfiles django-secrets

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
	        chmod 0600 $@; \
	    fi; \
	done

authfiles: $(SECRETSDIR) $(AUTHFILES)

django-secrets:
	@make -C ../../manager django-secrets SECRETSDIR=$(SECRETSDIR)
