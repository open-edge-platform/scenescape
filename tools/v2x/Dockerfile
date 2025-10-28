# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mqtt_psm.py .

RUN useradd -m -u 1000 psm && \
    chown -R psm:psm /app

USER psm

CMD ["python", "mqtt_psm.py"]
