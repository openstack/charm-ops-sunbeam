#!/usr/bin/env bash

[ -e .tox/cookie/bin/activate ] || tox -e cookie
source .tox/cookie/bin/activate
shared_code/sunbeam-charm-init.py $@
