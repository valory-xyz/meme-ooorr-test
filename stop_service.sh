#!/bin/bash

# ------------------------------------------------------------------------------
#
#   Copyright 2024 David Vilela Freire
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

REPO_PATH=$PWD
MEMEOOORR_DB=$REPO_PATH/memeooorr/abci_build/persistent_data/logs/memeooorr.db
TWITTER_COOKIES=$REPO_PATH/memeooorr/abci_build/persistent_data/logs/twikit_cookies.json

BUILD_DIR=$(ls -d memeooorr/abci_build*/)
poetry run autonomy deploy stop --build-dir "$BUILD_DIR"; cd ..

# Backup db
if test -e $MEMEOOORR_DB; then
  echo "Creating database backup"
  cp $MEMEOOORR_DB $REPO_PATH
fi

# Backup cookies
if test -e $TWITTER_COOKIES; then
  echo "Creating cookies backup"
  cp $TWITTER_COOKIES $REPO_PATH
fi