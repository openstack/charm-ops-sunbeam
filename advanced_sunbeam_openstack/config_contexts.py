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

# XXX Dulpicating definition in relation handlers
ERASURE_CODED = "erasure-coded"
REPLICATED = "replacated"


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
        return {
            "name": self.charm.service_name,
            "wsgi_admin_script": self.charm.wsgi_admin_script,
            "wsgi_public_script": self.charm.wsgi_public_script,
        }


class CephConfigurationContext(ConfigContext):
    """Ceph configuration context."""

    def context(self) -> None:
        """Ceph configuration context."""
        config = self.charm.model.config.get
        ctxt = {}
        if config("pool-type") and config("pool-type") == "erasure-coded":
            base_pool_name = config("rbd-pool") or config("rbd-pool-name")
            if not base_pool_name:
                base_pool_name = self.charm.app.name
            ctxt["rbd_default_data_pool"] = base_pool_name
        return ctxt


class CinderCephConfigurationContext(ConfigContext):
    """Cinder Ceph configuration context."""

    def context(self) -> None:
        """Cinder Ceph configuration context."""
        config = self.charm.model.config.get
        data_pool_name = config('rbd-pool-name') or self.charm.app.name
        if config('pool-type') == ERASURE_CODED:
            pool_name = (
                config('ec-rbd-metadata-pool') or
                f"{data_pool_name}-metadata"
            )
        else:
            pool_name = data_pool_name
        backend_name = config('volume-backend-name') or self.charm.app.name
        # TODO:
        # secret_uuid needs to be generated and shared for the app
        return {
            'cluster_name': self.charm.app.name,
            'rbd_pool': pool_name,
            'rbd_user': self.charm.app.name,
            'backend_name': backend_name,
            'backend_availability_zone': config('backend-availability-zone'),
        }
