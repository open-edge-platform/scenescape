# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

.PHONY: clean docs help install docserve test cpp-tests
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
	rm -r build-rv-tests || true

docshtml:
	$(MAKE) -C docs html

docspdf:
	$(MAKE) -C docs latexpdf

test:
	python3 setup.py test

cpp-tests:
	cmake -S . -B build-rv-tests -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=OFF
	cmake --build build-rv-tests
	cd build-rv-tests && ctest -V

docserve:
	cd docs/_build/html && python3 -m http.server 8000
