# Copyright 2022 Canonical Ltd.
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

"""Base classes for defining OVN Pebble handlers."""

from typing import (
    List,
)

from ops.model import (
    ActiveStatus,
)

from .. import container_handlers as sunbeam_chandlers
from .. import core as sunbeam_core


class OVNPebbleHandler(sunbeam_chandlers.ServicePebbleHandler):
    """Common class for OVN services."""

    @property
    def wrapper_script(self) -> str:
        """Path to OVN service wrapper."""
        raise NotImplementedError

    @property
    def status_command(self) -> str:
        """Command to check status of service."""
        raise NotImplementedError

    def init_service(self, context: sunbeam_core.OPSCharmContexts) -> None:
        """Initialise service ready for use.

        Write configuration files to the container and record
        that service is ready for us.

        NOTE: Override default to services being automatically started
        """
        self.setup_dirs()
        self.write_config(context)
        self.status.set(ActiveStatus(""))

    @property
    def service_description(self) -> str:
        """Return a short description of service e.g. OVN Southbound DB."""
        raise NotImplementedError

    def get_layer(self) -> dict:
        """Pebble configuration layer for OVN service.

        :returns: pebble layer configuration for service
        :rtype: dict
        """
        return {
            "summary": f"{self.service_description} service",
            "description": (
                "Pebble config layer for " f"{self.service_description}"
            ),
            "services": {
                self.service_name: {
                    "override": "replace",
                    "summary": f"{self.service_description}",
                    "command": f"bash {self.wrapper_script}",
                    "startup": "disabled",
                },
            },
        }

    def get_healthcheck_layer(self) -> dict:
        """Health check pebble layer.

        :returns: pebble health check layer configuration for OVN service
        :rtype: dict
        """
        return {
            "checks": {
                "online": {
                    "override": "replace",
                    "level": "ready",
                    "exec": {"command": f"{self.status_command}"},
                },
            }
        }

    @property
    def directories(self) -> List[sunbeam_chandlers.ContainerDir]:
        """Directories to creete in container."""
        return [
            sunbeam_chandlers.ContainerDir("/etc/ovn", "root", "root"),
            sunbeam_chandlers.ContainerDir("/run/ovn", "root", "root"),
            sunbeam_chandlers.ContainerDir("/var/lib/ovn", "root", "root"),
            sunbeam_chandlers.ContainerDir("/var/log/ovn", "root", "root"),
        ]

    def default_container_configs(
        self,
    ) -> List[sunbeam_core.ContainerConfigFile]:
        """Files to render into containers."""
        return [
            sunbeam_core.ContainerConfigFile(
                self.wrapper_script, "root", "root"
            ),
            sunbeam_core.ContainerConfigFile(
                "/etc/ovn/key_host", "root", "root"
            ),
            sunbeam_core.ContainerConfigFile(
                "/etc/ovn/cert_host", "root", "root"
            ),
            sunbeam_core.ContainerConfigFile(
                "/etc/ovn/ovn-central.crt", "root", "root"
            ),
        ]
