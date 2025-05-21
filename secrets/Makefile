# Makefile for managing secrets
# Copyright (C) 2024 Intel Corporation

SHELL=/bin/bash
SECRETSDIR ?= ../secrets
MQTTUSERS ?= "percebro.auth=cameras controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"

.PHONY: all secrets django-secrets authfiles

all: secrets

secrets: django-secrets authfiles
	@chmod go-rwx $(SECRETSDIR)

# Generate Django secrets
django-secrets: $(SECRETSDIR)/django/secrets.py

$(SECRETSDIR)/django/secrets.py:
	@mkdir -p $(SECRETSDIR)/django
	@echo -n SECRET_KEY= > $@
	@python3 -c 'import secrets; print("\x27" + "".join([secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]) + "\x27")' >> $@
	@echo "DATABASE_PASSWORD='$${DBPASS:-$$(openssl rand -base64 12)}'" >> $@
	@chmod 0600 $@

# Generate MQTT authentication files
authfiles: $(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))

$(SECRETSDIR)/%.auth:
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

authfiles: $(AUTHFILES)
