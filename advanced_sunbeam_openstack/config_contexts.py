# Copyright 2021 Canonical Ltd.
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

"""Base classes for defining a charm using the Operator framework.

ConfigContext objects can be used when rendering templates. They idea is to
create reusable contexts which translate charm config, deployment state etc.
These are not specific to a relation.
"""

import logging

logger = logging.getLogger(__name__)


class ConfigContext():

    def __init__(self, charm, namespace):
        self.charm = charm
        self.namespace = namespace
        for k, v in self.context().items():
            k = k.replace('-', '_')
            setattr(self, k, v)

    @property
    def ready(self):
        return True

    def context(self):
        raise NotImplementedError


class CharmConfigContext(ConfigContext):
    """A context containing all of the charms config options"""

    def context(self) -> dict:
        return self.charm.config


class WSGIWorkerConfigContext(ConfigContext):

    def context(self) -> dict:
        """A context containing WSGI configuration options"""
        return {
            'name': self.charm.service_name,
            'wsgi_admin_script': self.charm.wsgi_admin_script,
            'wsgi_public_script': self.charm.wsgi_public_script}
