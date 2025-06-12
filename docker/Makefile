# Copyright (C) 2021-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

SHELL=/bin/bash
IMAGE=scenescape
VERSION:=$(shell cat ../version.txt)
CERTDOMAIN=scenescape.intel.com
SECRETSDIR=../secrets
MQTTUSERS="percebro.auth=cameras controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"
AUTHFILES=$(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))

default: secrets

secrets: certificate django-secrets authfiles
	chmod go-rwx $(SECRETSDIR)

certificate:
	CERTDOMAIN=$(CERTDOMAIN) make -C ../tools/certificates

django-secrets: $(SECRETSDIR)/django/secrets.py

$(SECRETSDIR)/django/secrets.py:
	mkdir -p $(SECRETSDIR)/django
	echo -n SECRET_KEY= > $@
	python3 -c 'import secrets; print("\x27" + "".join([secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]) + "\x27")' >> $@
	echo "DATABASE_PASSWORD='$${DBPASS:-$$(openssl rand -base64 12)}'" >> $@
	chmod 0600 $@

%.auth:
	set -e; \
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
