#!/bin/bash

set -eo pipefail

if [[ ! -d $1 || ! -w $1 ]] ; then
        echo "workspace is not writeable"
        exit 1
fi

export OPENHANDS_VER=${OPENHANDS_VER:-0.45}
export SANDBOX_VOLUMES=$1:/workspace
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock

podman run -it --rm \
    -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:${OPENHANDS_VER}-nikolaik \
    -e SANDBOX_VOLUMES=$SANDBOX_VOLUMES \
    -e LLM_API_KEY=ollama\
    -e LLM_MODEL=ollama/devstral:latest\
    -e LOG_ALL_EVENTS=true \
    -e LLM_BASE_URL=http://host.docker.internal:11434 \
    -v $XDG_RUNTIME_DIR/podman/podman.sock:/var/run/docker.sock \
    -v ~/.openhands:/.openhands \
    --add-host host.docker.internal:host-gateway \
    --name openhands-app-$(date +%Y%m%d%H%M%S) \
    docker.all-hands.dev/all-hands-ai/openhands:${OPENHANDS_VER} \
    python -m openhands.core.main -t "${@:2}"