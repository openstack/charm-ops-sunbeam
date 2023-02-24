# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Helpers for controlling whether jobs should run.

In general it is better for a command to be a noop if run when it is not
needed but in some cases the commands are expensive or disruptive in which
case these helpers can limit how frequently they are run.
"""

import logging
import time
from functools import (
    wraps,
)

import ops.framework

import ops_sunbeam

logger = logging.getLogger(__name__)


def run_once_per_unit(label):
    """Run once per instantiation of a unit.

    This is designed for commands which only need to be run once on each
    instantiation of a unit.

    Note: This decorator can only be used within a charm derived from
          ops_sunbeam.charm.OSBaseOperatorCharm.

    Example usage:

        class MyCharm(ops_sunbeam.charm.OSBaseOperatorCharm):
            ...
            @run_once_per_unit('a2enmod')
            def enable_apache_module(self):
                check_call(['a2enmod', 'wsgi'])
    """

    def wrap(f):
        @wraps(f)
        def wrapped_f(
            charm: ops_sunbeam.charm.OSBaseOperatorCharm, *args, **kwargs
        ):
            """Run once decorator.

            :param charm: Instance of charm
            """
            storage = LocalJobStorage(charm._state)
            if label in storage:
                logging.warning(
                    f"Not running {label}, it has run previously for this unit"
                )
            else:
                logging.warning(
                    f"Running {label}, it has not run on this unit before"
                )
                f(charm, *args, **kwargs)
                storage.add(label)

        return wrapped_f

    return wrap


class LocalJobStorage:
    """Class to store job info of jobs run on the local unit."""

    def __init__(self, storage: ops.framework.BoundStoredState):
        """Setup job history storage."""
        self.storage = storage
        try:
            self.storage.run_once
        except AttributeError:
            self.storage.run_once = {}

    def get_labels(self):
        """Return all job entries."""
        return self.storage.run_once

    def __contains__(self, key):
        """Check if label is in list or run jobs."""
        return key in self.get_labels().keys()

    def add(self, key):
        """Add the label of job that has run."""
        self.storage.run_once[key] = str(time.time())
