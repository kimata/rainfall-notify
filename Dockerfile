FROM python:3.11-bookworm AS build

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    curl \
    build-essential \
    libasound2-dev

ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH=/root/.rye/shims/:$PATH

RUN curl -sSf https://rye.astral.sh/get | RYE_NO_AUTO_INSTALL=1 RYE_INSTALL_OPTION="--yes" bash

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=README.md,target=README.md \
    rye lock

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.lock

FROM python:3.11-slim-bookworm AS prod

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    alsa-utils

ARG IMAGE_BUILD_DATE

ENV TZ=Asia/Tokyo
ENV IMAGE_BUILD_DATE=${IMAGE_BUILD_DATE}

COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

WORKDIR /opt/rainfall-notify

COPY . .

COPY conf/asound.conf /etc

CMD ["./src/app.py"]
