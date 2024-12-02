#!/usr/bin/env bash

# Remove previous service build
if test -d memeooorr; then
  echo "Removing previous service build"
  sudo rm -r memeooorr
fi

# Push packages and fetch service
make clean

autonomy push-all

autonomy fetch --local --service dvilela/memeooorr && cd memeooorr

# Build the image
autonomy init --reset --author dvilela --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"
autonomy build-image