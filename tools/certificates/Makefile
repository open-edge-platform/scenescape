# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL=/bin/bash
SECRETSDIR ?= ../../manager/secrets
CASECRETSDIR ?= $(SECRETSDIR)
HOST ?= default
HOSTSUFFIX ?=
CERTDOMAIN ?= scenescape.intel.com

default: deploy-certificates

#.PHONY targets won't be skipped if files with these names happen to exist
.PHONY: default ca deploy-certificates deploy-csr
.PHONY: broker-cert web-cert reid-cert reid-s-cert autocalibration-cert mapping-cert
.PHONY: broker-csr web-csr reid-csr reid-s-csr autocalibration-csr mapping-csr

#.SECONDARY prevents make from deleting files created by intermediate targets
.SECONDARY:

deploy-certificates: ca broker-cert web-cert reid-cert reid-s-cert autocalibration-cert mapping-cert

deploy-csr: broker-csr web-csr reid-csr reid-s-csr autocalibration-csr mapping-csr

# EXTRA_HOSTS: additional DNS SANs (space-separated host labels, no domain).
# Used by multi-controller hierarchy tests (parent-/child*-web/broker, reid-*).
broker-cert: HOST=broker
broker-cert: KEY_USAGE=serverAuth
broker-cert: EXTRA_HOSTS=parent-broker child1-broker child2-broker
broker-cert: \
	$(SECRETSDIR)/certs/scenescape-broker.key \
	$(SECRETSDIR)/certs/scenescape-broker.crt \

web-cert: HOST=web
web-cert: KEY_USAGE=serverAuth
web-cert: EXTRA_HOSTS=parent-web child1-web child2-web
web-cert: \
	$(SECRETSDIR)/certs/scenescape-web.key \
	$(SECRETSDIR)/certs/scenescape-web.crt \

reid-cert: HOST=reid
reid-cert: KEY_USAGE=clientAuth
reid-cert: \
	$(SECRETSDIR)/certs/scenescape-reid.key \
	$(SECRETSDIR)/certs/scenescape-reid.crt \

reid-s-cert: HOST=reid
reid-s-cert: KEY_USAGE=serverAuth
reid-s-cert: EXTRA_HOSTS=reid-shared reid-a reid-b
reid-s-cert: \
	$(SECRETSDIR)/certs/scenescape-reid-s.key \
	$(SECRETSDIR)/certs/scenescape-reid-s.crt \

autocalibration-cert: HOST=autocalibration
autocalibration-cert: KEY_USAGE=serverAuth
autocalibration-cert: \
	$(SECRETSDIR)/certs/scenescape-autocalibration.key \
	$(SECRETSDIR)/certs/scenescape-autocalibration.crt \

mapping-cert: HOST=mapping
mapping-cert: KEY_USAGE=serverAuth
mapping-cert: \
	$(SECRETSDIR)/certs/scenescape-mapping.key \
	$(SECRETSDIR)/certs/scenescape-mapping.crt \

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

reid-csr: HOST=reid
reid-csr: KEY_USAGE=clientAuth
reid-csr: \
	$(SECRETSDIR)/certs/scenescape-reid.key \
	$(SECRETSDIR)/certs/scenescape-reid.csr \

reid-s-csr: HOST=reid
reid-s-csr: KEY_USAGE=serverAuth
reid-s-csr: \
	$(SECRETSDIR)/certs/scenescape-reid-s.key \
	$(SECRETSDIR)/certs/scenescape-reid-s.csr \

autocalibration-csr: HOST=autocalibration
autocalibration-csr: KEY_USAGE=serverAuth
autocalibration-csr: \
	$(SECRETSDIR)/certs/scenescape-autocalibration.key \
	$(SECRETSDIR)/certs/scenescape-autocalibration.csr \

mapping-csr: HOST=mapping
mapping-csr: KEY_USAGE=serverAuth
mapping-csr: \
	$(SECRETSDIR)/certs/scenescape-mapping.key \
	$(SECRETSDIR)/certs/scenescape-mapping.csr \

ca: $(CASECRETSDIR)/certs/scenescape-ca.pem

$(CASECRETSDIR)/ca/scenescape-ca.key:
	@echo Generating root CA key
	@mkdir -p $(CASECRETSDIR)/ca
	@if [ -n "$(CERTPASS)" ] ; then PASSFLAGS="-passout pass:$(CERTPASS)" ; fi ; \
	openssl ecparam -name secp384r1 -genkey | openssl ec -aes256 $${PASSFLAGS} -out $@
	@chmod 0644 $@

$(CASECRETSDIR)/certs/scenescape-ca.pem: $(CASECRETSDIR)/ca/scenescape-ca.key
	@echo Generating root CA certificate
	@mkdir -p $(CASECRETSDIR)/certs
	@if [ -n "$(CERTPASS)" ] ; then PASSFLAGS="-passin pass:$(CERTPASS)" ; fi ; \
	openssl req $${PASSFLAGS} -x509 -new -key $< -days 1825 -out $@ \
	  -subj "/CN=ca.$(CERTDOMAIN)"
	@chmod 0644 $@

$(SECRETSDIR)/certs/%.key:
	@echo Generating $*.key
	@mkdir -p $(SECRETSDIR)/certs
	@openssl ecparam -name secp384r1 -genkey -noout -out $@
	@chmod 0644 $@

$(SECRETSDIR)/certs/%.csr: $(SECRETSDIR)/certs/%.key
	@SUBJECT_ALT_NAMES="DNS.1=$(HOST)$(HOSTSUFFIX).$(CERTDOMAIN)" ; \
	i=2 ; for h in $(EXTRA_HOSTS) ; do \
	  SUBJECT_ALT_NAMES="$${SUBJECT_ALT_NAMES}\nDNS.$${i}=$${h}.$(CERTDOMAIN)" ; \
	  i=$$((i+1)) ; \
	done ; \
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
	i=2 ; for h in $(EXTRA_HOSTS) ; do \
	  SUBJECT_ALT_NAMES="$${SUBJECT_ALT_NAMES}\nDNS.$${i}=$${h}.$(CERTDOMAIN)" ; \
	  i=$$((i+1)) ; \
	done ; \
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
