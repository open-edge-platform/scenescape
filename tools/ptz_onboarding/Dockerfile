# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim
WORKDIR /opt/ptz_onboarding
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
ENTRYPOINT ["python", "/opt/ptz_onboarding/ptz.py"]
