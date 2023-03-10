#!/usr/bin/env python3

# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test charms for unit tests."""

import os
import sys
import tempfile
from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    import ops.framework

from typing import (
    List,
)

sys.path.append("unit_tests/lib")  # noqa
sys.path.append("src")  # noqa

import ops_sunbeam.charm as sunbeam_charm
import ops_sunbeam.container_handlers as sunbeam_chandlers

CHARM_CONFIG = """
options:
  debug:
    default: True
    description: Enable debug logging.
    type: boolean
  region:
    default: RegionOne
    description: Region
    type: string
"""

INITIAL_CHARM_CONFIG = {"debug": "true", "region": "RegionOne"}

CHARM_METADATA = """
name: my-service
version: 3
bases:
  - name: ubuntu
    channel: 20.04/stable
tags:
  - openstack
  - identity
  - misc

subordinate: false

containers:
  my-service:
    resource: mysvc-image
    mounts:
      - storage: db
        location: /var/lib/mysvc

storage:
  logs:
    type: filesystem
  db:
    type: filesystem

resources:
  mysvc-image:
    type: oci-image
"""

API_CHARM_METADATA = """
name: my-service
version: 3
bases:
  - name: ubuntu
    channel: 20.04/stable
tags:
  - openstack
  - identity
  - misc

subordinate: false

requires:
  database:
    interface: mysql_client
    limit: 1
  ingress-internal:
    interface: ingress
    limit: 1
  ingress-public:
    interface: ingress
    limit: 1
  amqp:
    interface: rabbitmq
  identity-service:
    interface: keystone
  identity-credentials:
    interface: keystone-credentials
    limit: 1

peers:
  peers:
    interface: mysvc-peer

containers:
  my-service:
    resource: mysvc-image
    mounts:
      - storage: db
        location: /var/lib/mysvc

storage:
  logs:
    type: filesystem
  db:
    type: filesystem

resources:
  mysvc-image:
    type: oci-image
"""


class MyCharm(sunbeam_charm.OSBaseOperatorCharm):
    """Test charm for testing OSBaseOperatorCharm."""

    service_name = "my-service"

    def __init__(self, framework: "ops.framework.Framework") -> None:
        """Run constructor."""
        self.seen_events = []
        self.render_calls = []
        self._template_dir = self._setup_templates()
        super().__init__(framework)

    def _log_event(self, event: "ops.framework.EventBase") -> None:
        """Log events."""
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(
        self, event: "ops.framework.EventBase"
    ) -> None:
        """Log pebble ready event."""
        self._log_event(event)
        super()._on_service_pebble_ready(event)

    def _on_config_changed(self, event: "ops.framework.EventBase") -> None:
        """Log config changed event."""
        self._log_event(event)
        super()._on_config_changed(event)

    def configure_charm(self, event: "ops.framework.EventBase") -> None:
        """Log configure_charm call."""
        self._log_event(event)
        super().configure_charm(event)

    @property
    def public_ingress_port(self) -> int:
        """Charms default port."""
        return 789

    def _setup_templates(self) -> str:
        """Run temp templates dir setup."""
        tmpdir = tempfile.mkdtemp()
        _template_dir = f"{tmpdir}/templates"
        os.mkdir(_template_dir)
        with open(f"{_template_dir}/my-service.conf.j2", "w") as f:
            f.write("")
        return _template_dir

    @property
    def template_dir(self) -> str:
        """Temp templates dir."""
        return self._template_dir


TEMPLATE_CONTENTS = """
{{ wsgi_config.wsgi_admin_script }}
{{ database.database_password }}
{{ options.debug }}
{{ amqp.transport_url }}
{{ amqp.hostname }}
{{ identity_service.service_password }}
{{ peers.foo }}
"""


class MyAPICharm(sunbeam_charm.OSBaseOperatorAPICharm):
    """Test charm for testing OSBaseOperatorAPICharm."""

    service_name = "my-service"
    wsgi_admin_script = "/bin/wsgi_admin"
    wsgi_public_script = "/bin/wsgi_public"
    mandatory_relations = {
        "database",
        "amqp",
        "identity-service",
        "ingress-public",
    }

    def __init__(self, framework: "ops.framework.Framework") -> None:
        """Run constructor."""
        self.seen_events = []
        self.render_calls = []
        self._template_dir = self._setup_templates()
        super().__init__(framework)

    def _setup_templates(self) -> str:
        """Run temp templates dir setup."""
        tmpdir = tempfile.mkdtemp()
        _template_dir = f"{tmpdir}/templates"
        os.mkdir(_template_dir)
        with open(f"{_template_dir}/my-service.conf.j2", "w") as f:
            f.write(TEMPLATE_CONTENTS)
        with open(f"{_template_dir}/wsgi-my-service.conf.j2", "w") as f:
            f.write(TEMPLATE_CONTENTS)
        return _template_dir

    def _log_event(self, event: "ops.framework.EventBase") -> None:
        """Log events."""
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(
        self, event: "ops.framework.EventBase"
    ) -> None:
        """Log pebble ready event."""
        self._log_event(event)
        super()._on_service_pebble_ready(event)

    def _on_config_changed(self, event: "ops.framework.EventBase") -> None:
        """Log config changed event."""
        self._log_event(event)
        super()._on_config_changed(event)

    @property
    def default_public_ingress_port(self) -> int:
        """Charms default port."""
        return 789

    @property
    def template_dir(self) -> str:
        """Templates dir."""
        return self._template_dir

    @property
    def healthcheck_http_url(self) -> str:
        """Healthcheck HTTP URL for the service."""
        return f"http://localhost:{self.default_public_ingress_port}/v3"


class MultiSvcPebbleHandler(sunbeam_chandlers.ServicePebbleHandler):
    """Test pebble handler for multi service charm."""

    def get_layer(self) -> dict:
        """Glance API service pebble layer.

        :returns: pebble layer configuration for glance api service
        """
        return {
            "summary": f"{self.service_name} layer",
            "description": "pebble config layer for glance api service",
            "services": {
                f"{self.service_name}": {
                    "override": "replace",
                    "summary": f"{self.service_name} standalone",
                    "command": "/usr/bin/glance-api",
                    "startup": "disabled",
                },
                "apache forwarder": {
                    "override": "replace",
                    "summary": "apache",
                    "command": "/usr/sbin/apache2ctl -DFOREGROUND",
                    "startup": "disabled",
                },
            },
        }


class TestMultiSvcCharm(MyAPICharm):
    """Test class of multi service charm."""

    def get_pebble_handlers(self) -> List[sunbeam_chandlers.PebbleHandler]:
        """Pebble handlers for the service."""
        return [
            MultiSvcPebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.configure_charm,
            )
        ]
