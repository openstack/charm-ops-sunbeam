#!/usr/bin/env python3

# Copyright 2023 Canonical Ltd.
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

"""Charm definitions for scenatio tests."""

import ops_sunbeam.charm as sunbeam_charm
import ops_sunbeam.container_handlers as sunbeam_chandlers
import ops_sunbeam.core as sunbeam_core


class MyCharm(sunbeam_charm.OSBaseOperatorCharm):
    """Test charm for testing OSBaseOperatorCharm."""

    service_name = "my-service"


MyCharm_Metadata = {
    "name": "my-service",
    "version": "3",
    "bases": {"name": "ubuntu", "channel": "20.04/stable"},
    "tags": ["openstack", "identity", "misc"],
    "subordinate": False,
}


class MyCharmMulti(sunbeam_charm.OSBaseOperatorCharm):
    """Test charm for testing OSBaseOperatorCharm."""

    # mandatory_relations = {"amqp", "database", "identity-credentials"}
    mandatory_relations = {"amqp", "identity-credentials"}
    service_name = "my-service"


MyCharmMulti_Metadata = {
    "name": "my-service",
    "version": "3",
    "bases": {"name": "ubuntu", "channel": "20.04/stable"},
    "tags": ["openstack", "identity", "misc"],
    "subordinate": False,
    "requires": {
        #        "database": {"interface": "mysql_client", "limit": 1},
        "amqp": {"interface": "rabbitmq"},
        "identity-credentials": {
            "interface": "keystone-credentials",
            "limit": 1,
        },
    },
}


class NovaSchedulerPebbleHandler(sunbeam_chandlers.ServicePebbleHandler):
    """Pebble handler for Nova scheduler."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_service_check = True

    def get_layer(self) -> dict:
        """Nova Scheduler service layer.

        :returns: pebble layer configuration for scheduler service
        :rtype: dict
        """
        return {
            "summary": "nova scheduler layer",
            "description": "pebble configuration for nova services",
            "services": {
                "nova-scheduler": {
                    "override": "replace",
                    "summary": "Nova Scheduler",
                    "command": "nova-scheduler",
                    "startup": "enabled",
                    "user": "nova",
                    "group": "nova",
                }
            },
        }


class NovaConductorPebbleHandler(sunbeam_chandlers.ServicePebbleHandler):
    """Pebble handler for Nova Conductor container."""

    def get_layer(self):
        """Nova Conductor service.

        :returns: pebble service layer configuration for conductor service
        :rtype: dict
        """
        return {
            "summary": "nova conductor layer",
            "description": "pebble configuration for nova services",
            "services": {
                "nova-conductor": {
                    "override": "replace",
                    "summary": "Nova Conductor",
                    "command": "nova-conductor",
                    "startup": "enabled",
                    "user": "nova",
                    "group": "nova",
                }
            },
        }


class MyCharmK8S(sunbeam_charm.OSBaseOperatorCharmK8S):
    """Test charm for testing OSBaseOperatorCharm."""

    # mandatory_relations = {"amqp", "database", "identity-credentials"}
    mandatory_relations = {"amqp", "identity-credentials"}
    service_name = "my-service"

    def get_pebble_handlers(self):
        """Pebble handlers for the operator."""
        return [
            NovaSchedulerPebbleHandler(
                self,
                "container1",
                "container1-svc",
                self.container_configs,
                "/tmp",
                self.configure_charm,
            ),
            NovaConductorPebbleHandler(
                self,
                "container2",
                "container2-svc",
                self.container_configs,
                "/tmp",
                self.configure_charm,
            ),
        ]


MyCharmK8S_Metadata = {
    "name": "my-service",
    "version": "3",
    "bases": {"name": "ubuntu", "channel": "20.04/stable"},
    "tags": ["openstack", "identity", "misc"],
    "subordinate": False,
    "containers": {
        "container1": {"resource": "container1-image"},
        "container2": {"resource": "container2-image"},
    },
    "requires": {
        #        "database": {"interface": "mysql_client", "limit": 1},
        "amqp": {"interface": "rabbitmq"},
        "identity-credentials": {
            "interface": "keystone-credentials",
            "limit": 1,
        },
    },
}


class MyCharmK8SAPI(sunbeam_charm.OSBaseOperatorCharmK8S):
    """Test charm for testing OSBaseOperatorCharm."""

    # mandatory_relations = {"amqp", "database", "identity-credentials"}
    mandatory_relations = {"amqp", "identity-credentials"}
    service_name = "my-service"


MyCharmK8SAPI_Metadata = {
    "name": "my-service",
    "version": "3",
    "bases": {"name": "ubuntu", "channel": "20.04/stable"},
    "tags": ["openstack", "identity", "misc"],
    "subordinate": False,
    "containers": {
        "my-service": {"resource": "container1-image"},
    },
    "requires": {
        #        "database": {"interface": "mysql_client", "limit": 1},
        "amqp": {"interface": "rabbitmq"},
        "identity-credentials": {
            "interface": "keystone-credentials",
        },
    },
}
