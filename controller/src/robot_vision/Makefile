# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

.PHONY: clean docs help install docserve test
.DEFAULT_GOAL := test

clean:
	python3 setup.py clean
	rm -r build || true
	rm -r build_cmake || true
	rm -r python/src/robot_vision.egg-info || true
	rm -r .eggs || true
	rm -r docs/_build/ || true
	rm -r docs/generated/ || true
	find . -name __pycache__ | xargs rm -r || true

docshtml:
	$(MAKE) -C docs html

docspdf:
	$(MAKE) -C docs latexpdf

test:
	python3 setup.py test

docserve:
	cd docs/_build/html && python3 -m http.server 8000
