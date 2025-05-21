SHELL=/bin/bash
.SHELLFLAGS=-o pipefail -c
IMAGE=scenescape
VERSION:=$(shell cat ../version.txt)

TEST_DATA=test_data
TESTS_DIRECTORY=tests
COVERAGE_CMD=coverage run
COVERAGE_DATA_FILE=$(TESTS_DIRECTORY)/tests/.coverage_unit_$@
COMBINED_COVERAGE_DATA_FILE=.coverage_combine
UNIT_TESTS_COMBINED_FILE=$(TESTS_DIRECTORY)/tests/$(COMBINED_COVERAGE_DATA_FILE)
COVERAGE_RC_FILE=tests/config.coveragerc
UNIT_TEST_COVERAGE_ARGS=--rcfile=$(COVERAGE_RC_FILE) -a
UNIT_TEST_COVERAGE_CMD=COVERAGE_FILE=$(COVERAGE_DATA_FILE) $(COVERAGE_CMD) $(UNIT_TEST_COVERAGE_ARGS)
GENERATE_JUNITXML_UNITTEST=-o junit_logging=all --junitxml reports/test_reports/unit-tests/$@.xml

define unit-recipe=
	$(eval TEST_FOLDER=$1)
	$(eval DOCKER_IMAGE=$2)
	$(eval DOCKER_IMAGE=$(if $(DOCKER_IMAGE), $(DOCKER_IMAGE), $(IMAGE)))
	$(eval LOGFILE=$(TEST_DATA)/unit/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; pwd \
	  ; cd .. \
	  ; pwd \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; if [ ! -e scenescape-start ] && [ ! -h scenescape-start ]; then \
	      echo "Creating symlink to scenescape-start script"; \
	      ln -s ../docker/scenescape-start scenescape-start; \
	    else \
	      echo "scenescape-start already exists."; \
	    fi \
	  ; ./scenescape-start --image $(DOCKER_IMAGE) sh -c "$(UNIT_TEST_COVERAGE_CMD) --source=percebro/ -m pytest -s $(GENERATE_JUNITXML_UNITTEST) $(TEST_FOLDER)/" 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@
endef

tests: \
  realsense-unit \
  videosource-unit \

realsense-unit: # SAIL-T572
	$(call unit-recipe, tests/realsense, $(IMAGE)-percebro)

videosource-unit: # SAIL-T569
	$(call unit-recipe, tests/videosource, $(IMAGE)-percebro)
