# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

SHELL=/bin/bash
SECRETSDIR ?= ../../manager/secrets
CASECRETSDIR ?= $(SECRETSDIR)
HOST ?= default
HOSTSUFFIX ?=
CERTDOMAIN ?= scenescape.intel.com

default: deploy-certificates

#.PHONY targets won't be skipped if files with these names happen to exist
.PHONY: default ca deploy-certificates deploy-csr
.PHONY: broker-cert web-cert vdms-c-cert vdms-s-cert
.PHONY: broker-csr web-csr vdms-c-csr vdms-s-csr

#.SECONDARY prevents make from deleting files created by intermediate targets
.SECONDARY:

deploy-certificates: ca broker-cert web-cert vdms-c-cert vdms-s-cert

deploy-csr: broker-csr web-csr vdms-c-csr vdms-s-csr

broker-cert: HOST=broker
broker-cert: KEY_USAGE=serverAuth
broker-cert: \
	$(SECRETSDIR)/certs/scenescape-broker.key \
	$(SECRETSDIR)/certs/scenescape-broker.crt \

web-cert: HOST=web
web-cert: KEY_USAGE=serverAuth
web-cert: \
	$(SECRETSDIR)/certs/scenescape-web.key \
	$(SECRETSDIR)/certs/scenescape-web.crt \

vdms-c-cert: HOST=vdms-c
vdms-c-cert: KEY_USAGE=clientAuth
vdms-c-cert: \
	$(SECRETSDIR)/certs/scenescape-vdms-c.key \
	$(SECRETSDIR)/certs/scenescape-vdms-c.crt \

vdms-s-cert: HOST=vdms
vdms-s-cert: KEY_USAGE=serverAuth
vdms-s-cert: \
	$(SECRETSDIR)/certs/scenescape-vdms-s.key \
	$(SECRETSDIR)/certs/scenescape-vdms-s.crt \

broker-csr: HOST=broker
broker-csr: KEY_USAGE=serverAuth
broker-csr: \
	$(SECRETSDIR)/certs/scenescape-broker.key \
	$(SECRETSDIR)/certs/scenescape-broker.csr \

web-csr: HOST=web
web-csr: KEY_USAGE=serverAuth
web-csr: \
	$(SECRETSDIR)/certs/scenescape-web.key \
	$(SECRETSDIR)/certs/scenescape-web.csr \

vdms-c-csr: HOST=vdms-c
vdms-c-csr: KEY_USAGE=clientAuth
vdms-c-csr: \
	$(SECRETSDIR)/certs/scenescape-vdms-c.key \
	$(SECRETSDIR)/certs/scenescape-vdms-c.csr \

vdms-s-csr: HOST=vdms
vdms-s-csr: KEY_USAGE=serverAuth
vdms-s-csr: \
	$(SECRETSDIR)/certs/scenescape-vdms-s.key \
	$(SECRETSDIR)/certs/scenescape-vdms-s.csr \

ca: $(CASECRETSDIR)/certs/scenescape-ca.pem

$(CASECRETSDIR)/ca/scenescape-ca.key:
	@echo Generating root CA key
	@mkdir -p $(CASECRETSDIR)/ca
	@if [ -n "$(CERTPASS)" ] ; then PASSFLAGS="-passout pass:$(CERTPASS)" ; fi ; \
	openssl ecparam -name secp384r1 -genkey | openssl ec -aes256 $${PASSFLAGS} -out $@

$(CASECRETSDIR)/certs/scenescape-ca.pem: $(CASECRETSDIR)/ca/scenescape-ca.key
	@echo Generating root CA certificate
	@mkdir -p $(CASECRETSDIR)/certs
	@if [ -n "$(CERTPASS)" ] ; then PASSFLAGS="-passin pass:$(CERTPASS)" ; fi ; \
	openssl req $${PASSFLAGS} -x509 -new -key $< -days 1825 -out $@ \
	  -subj "/CN=ca.$(CERTDOMAIN)"

$(SECRETSDIR)/certs/%.key:
	@echo Generating $*.key
	@mkdir -p $(SECRETSDIR)/certs
	@openssl ecparam -name secp384r1 -genkey -noout -out $@

$(SECRETSDIR)/certs/%.csr: $(SECRETSDIR)/certs/%.key
	@SUBJECT_ALT_NAMES="DNS.1=$(HOST)$(HOSTSUFFIX).$(CERTDOMAIN)" ; \
	if [ -n "$(IP_SAN)" ] ; then SUBJECT_ALT_NAMES="$${SUBJECT_ALT_NAMES}\nIP.1=$(IP_SAN)"; fi ; \
	echo Generating CSR for $(HOST)$(HOSTSUFFIX).$(CERTDOMAIN) ; \
	mkdir -p $(SECRETSDIR)/certs ; \
	openssl req -new -out $@ -key $< \
	  -config <(\
	  sed -e "s/##CN##/$(HOST)$(HOSTSUFFIX).$(CERTDOMAIN)/" \
	  -e "s/##SAN##/$${SUBJECT_ALT_NAMES}/" \
	  -e "s/##KEYUSAGE##/$(KEY_USAGE)/" \
	  openssl.cnf)

$(SECRETSDIR)/certs/%.crt: $(SECRETSDIR)/certs/%.csr
	@SUBJECT_ALT_NAMES="DNS.1=$(HOST)$(HOSTSUFFIX).$(CERTDOMAIN)" ; \
	if [ -n "$(IP_SAN)" ] ; then SUBJECT_ALT_NAMES="$${SUBJECT_ALT_NAMES}\nIP.1=$(IP_SAN)" ; fi ; \
	echo Generating certificate for $(HOST)$(HOSTSUFFIX).$(CERTDOMAIN) ; \
	mkdir -p $(SECRETSDIR)/certs ; \
	if [ -n "$(CERTPASS)" ] ; then PASSFLAGS="-passin pass:$(CERTPASS)" ; fi ; \
	openssl x509 $${PASSFLAGS} -req -in $< \
	  -CA $(CASECRETSDIR)/certs/scenescape-ca.pem -CAkey $(CASECRETSDIR)/ca/scenescape-ca.key \
	  -CAcreateserial -out $@ -days 360 \
	  -extensions x509_ext -extfile <(\
	  sed -e "s/##SAN##/$${SUBJECT_ALT_NAMES}/" \
	  -e "s/##KEYUSAGE##/$(KEY_USAGE)/" \
	  openssl.cnf)

clean:
	@rm -rf $(SECRETSDIR)/certs $(CASECRETSDIR)/ca
