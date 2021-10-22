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

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import advanced_sunbeam_openstack.charm

logger = logging.getLogger(__name__)


class ConfigContext:
    """Base class used for creating a config context."""

    def __init__(
        self,
        charm: "advanced_sunbeam_openstack.charm.OSBaseOperatorCharm",
        namespace: str,
    ) -> None:
        """Run constructor."""
        self.charm = charm
        self.namespace = namespace
        for k, v in self.context().items():
            k = k.replace("-", "_")
            setattr(self, k, v)

    @property
    def ready(self) -> bool:
        """Whether the context has all the data is needs."""
        return True

    def context(self) -> dict:
        """Context used when rendering templates."""
        raise NotImplementedError


class CharmConfigContext(ConfigContext):
    """A context containing all of the charms config options."""

    def context(self) -> dict:
        """Charms config options."""
        return self.charm.config


class WSGIWorkerConfigContext(ConfigContext):
    """Configuration context for WSGI configuration."""

    def context(self) -> dict:
        """WSGI configuration options."""
        log_svc_name = self.charm.service_name.replace('-', '_')
        return {
            "name": self.charm.service_name,
            "user": self.charm.service_user,
            "group": self.charm.service_group,
            "wsgi_admin_script": self.charm.wsgi_admin_script,
            "wsgi_public_script": self.charm.wsgi_public_script,
            "error_log": f"/var/log/apache2/{log_svc_name}_error.log",
            "custom_log": f"/var/log/apache2/{log_svc_name}_access.log",
        }
