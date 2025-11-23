#!/bin/bash

if [[ $INSTALL_TOOLS == 1 ]]; then

  apt-get update
  apt-get install -y ca-certificates curl gnupg lsb-release

  # Add Docker’s official GPG key
  mkdir -m 0755 -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

  # Add the Docker apt repository
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
    $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce-cli docker-compose-plugin

fi