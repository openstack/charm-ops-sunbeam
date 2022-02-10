#!/usr/bin/env python3

# Copyright 2020 Canonical Ltd.
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

"""Module containing shared code to be used in a charms units tests."""

import yaml
import inspect
import io
import json
import ops
import os
import pathlib
import sys
import typing
import unittest
import collections

from mock import MagicMock, Mock, patch

sys.path.append("lib")  # noqa
sys.path.append("src")  # noqa

from ops import framework, model

from ops.testing import Harness, _TestingModelBackend, _TestingPebbleClient


class ContainerCalls:
    """Object to log container calls."""

    def __init__(self) -> None:
        """Init container calls."""
        self.push = collections.defaultdict(list)
        self.pull = collections.defaultdict(list)
        self.execute = collections.defaultdict(list)
        self.remove_path = collections.defaultdict(list)

    def add_push(self, container_name: str, call: typing.Dict) -> None:
        """Log a push call."""
        self.push[container_name].append(call)

    def add_pull(self, container_name: str, call: typing.Dict) -> None:
        """Log a pull call."""
        self.pull[container_name].append(call)

    def add_execute(self, container_name: str, call: typing.List) -> None:
        """Log a execute call."""
        self.execute[container_name].append(call)

    def add_remove_path(self, container_name: str, call: str) -> None:
        """Log a remove path call."""
        self.remove_path[container_name].append(call)

    def updated_files(self, container_name: str) -> typing.List:
        """Return a list of files that have been updated in a container."""
        return [c['path'] for c in self.push.get(container_name, [])]

    def file_update_calls(
        self,
        container_name: str,
        file_name: str
    ) -> typing.List:
        """Return the update call for File_name in container_name."""
        return [
            c
            for c in self.push.get(container_name, [])
            if c['path'] == file_name]


class CharmTestCase(unittest.TestCase):
    """Class to make mocking easier."""

    container_calls = {
        'push': {},
        'pull': [],
        'exec': [],
        'remove_path': []}

    def setUp(self, obj: 'typing.ANY', patches: 'typing.List') -> None:
        """Run constructor."""
        super().setUp()
        self.patches = patches
        self.obj = obj
        self.patch_all()

    def patch(self, method: 'typing.ANY') -> Mock:
        """Patch the named method on self.obj."""
        _m = patch.object(self.obj, method)
        mock = _m.start()
        self.addCleanup(_m.stop)
        return mock

    def patch_obj(self, obj: 'typing.ANY', method: 'typing.ANY') -> Mock:
        """Patch the named method on obj."""
        _m = patch.object(obj, method)
        mock = _m.start()
        self.addCleanup(_m.stop)
        return mock

    def patch_all(self) -> None:
        """Patch all objects in self.patches."""
        for method in self.patches:
            setattr(self, method, self.patch(method))


def add_base_amqp_relation(harness: Harness) -> str:
    """Add amqp relation."""
    rel_id = harness.add_relation("amqp", "rabbitmq")
    harness.add_relation_unit(rel_id, "rabbitmq/0")
    harness.add_relation_unit(rel_id, "rabbitmq/0")
    harness.update_relation_data(
        rel_id, "rabbitmq/0", {"ingress-address": "10.0.0.13"}
    )
    return rel_id


def add_amqp_relation_credentials(
    harness: Harness, rel_id: str
) -> None:
    """Add amqp data to amqp relation."""
    harness.update_relation_data(
        rel_id,
        "rabbitmq",
        {"hostname": "rabbithost1.local", "password": "rabbit.pass"},
    )


def add_base_identity_service_relation(harness: Harness) -> str:
    """Add identity-service relation."""
    rel_id = harness.add_relation("identity-service", "keystone")
    harness.add_relation_unit(rel_id, "keystone/0")
    harness.add_relation_unit(rel_id, "keystone/0")
    harness.update_relation_data(
        rel_id, "keystone/0", {"ingress-address": "10.0.0.33"}
    )
    return rel_id


def add_identity_service_relation_response(
    harness: Harness, rel_id: str
) -> None:
    """Add id service data to identity-service relation."""
    harness.update_relation_data(
        rel_id,
        "keystone",
        {
            "admin-domain-id": "admindomid1",
            "admin-project-id": "adminprojid1",
            "admin-user-id": "adminuserid1",
            "api-version": "3",
            "auth-host": "keystone.local",
            "auth-port": "12345",
            "auth-protocol": "http",
            "internal-host": "keystone.internal",
            "internal-port": "5000",
            "internal-protocol": "http",
            "service-domain": "servicedom",
            "service-domain_id": "svcdomid1",
            "service-host": "keystone.service",
            "service-password": "svcpass1",
            "service-port": "5000",
            "service-protocol": "http",
            "service-project": "svcproj1",
            "service-project-id": "svcprojid1",
            "service-username": "svcuser1",
        },
    )


def add_base_db_relation(harness: Harness) -> str:
    """Add db relation."""
    rel_id = harness.add_relation("shared-db", "mysql")
    harness.add_relation_unit(rel_id, "mysql/0")
    harness.add_relation_unit(rel_id, "mysql/0")
    harness.update_relation_data(
        rel_id, "mysql/0", {"ingress-address": "10.0.0.3"}
    )
    return rel_id


def add_db_relation_credentials(
    harness: Harness, rel_id: str
) -> None:
    """Add db credentials data to db relation."""
    harness.update_relation_data(
        rel_id,
        "mysql",
        {
            "databases": json.dumps(["db1"]),
            "data": json.dumps(
                {
                    "credentials": {
                        "username": "foo",
                        "password": "hardpassword",
                        "address": "10.0.0.10",
                    }
                }
            ),
        },
    )


def add_api_relations(harness: Harness) -> None:
    """Add standard relation to api charm."""
    add_db_relation_credentials(harness, add_base_db_relation(harness))
    add_amqp_relation_credentials(harness, add_base_amqp_relation(harness))
    add_identity_service_relation_response(
        harness, add_base_identity_service_relation(harness)
    )


def add_complete_db_relation(harness: Harness) -> None:
    """Add complete DB relation."""
    add_db_relation_credentials(
        harness,
        add_base_db_relation(harness))


def add_complete_identity_relation(harness: Harness) -> None:
    """Add complete Identity relation."""
    add_identity_service_relation_response(
        harness,
        add_base_identity_service_relation(harness))


def add_complete_amqp_relation(harness: Harness) -> None:
    """Add complete AMQP relation."""
    add_amqp_relation_credentials(
        harness,
        add_base_amqp_relation(harness))


def add_complete_peer_relation(harness: Harness) -> None:
    """Add complete peer relation."""
    harness.add_relation(
        'peers',
        harness.charm.app.name)


test_relations = {
    'shared-db': add_complete_db_relation,
    'amqp': add_complete_amqp_relation,
    'identity-service': add_complete_identity_relation,
    'peers': add_complete_peer_relation}


def add_all_relations(harness: Harness) -> None:
    """Add all the relations there are test relations for."""
    for key in harness._meta.relations.keys():
        if test_relations.get(key):
            test_relations[key](harness)


def set_all_pebbles_ready(harness: Harness) -> None:
    """Set all known pebble handlers to ready."""
    for container in harness._meta.containers:
        harness.container_pebble_ready(container)


def get_harness(
    charm_class: ops.charm.CharmBase,
    charm_metadata: str = None,
    container_calls: dict = None,
    charm_config: str = None,
    initial_charm_config: dict = None,
) -> Harness:
    """Return a testing harness."""

    class _OSTestingPebbleClient(_TestingPebbleClient):
        def push(
            self,
            path: str,
            source: typing.Union[bytes, str, typing.BinaryIO, typing.TextIO],
            *,
            encoding: str = "utf-8",
            make_dirs: bool = False,
            permissions: int = None,
            user_id: int = None,
            user: str = None,
            group_id: int = None,
            group: str = None,
        ) -> None:
            """Capture push events and store in container_calls."""
            container_calls.add_push(
                self.container_name,
                {
                    "path": path,
                    "source": source,
                    "permissions": permissions,
                    "user": user,
                    "group": group,
                }
            )

        def pull(self, path: str, *, encoding: str = "utf-8") -> None:
            """Capture pull events and store in container_calls."""
            container_calls.add_pull(
                self.container_name,
                path)
            reader = io.StringIO("0")
            return reader

        def remove_path(self, path: str, *, recursive: bool = False) -> None:
            """Capture remove events and store in container_calls."""
            container_calls.add_remove_path(
                self.container_name,
                path)

        def exec(
            self,
            command: typing.List[str],
            *,
            environment: typing.Dict[str, str] = None,
            working_dir: str = None,
            timeout: float = None,
            user_id: int = None,
            user: str = None,
            group_id: int = None,
            group: str = None,
            stdin: typing.Union[
                str, bytes, typing.TextIO, typing.BinaryIO] = None,
            stdout: typing.Union[typing.TextIO, typing.BinaryIO] = None,
            stderr: typing.Union[typing.TextIO, typing.BinaryIO] = None,
            encoding: str = 'utf-8',
            combine_stderr: bool = False
        ) -> None:
            container_calls.add_execute(
                self.container_name,
                command)
            process_mock = MagicMock()
            process_mock.wait_output.return_value = (None, None)
            return process_mock

    class _OSTestingModelBackend(_TestingModelBackend):
        def get_pebble(self, socket_path: str) -> _OSTestingPebbleClient:
            """Get the testing pebble client."""
            client = self._pebble_clients.get(socket_path, None)
            if client is None:
                client = _OSTestingPebbleClient(self)
                # Extract container name from:
                # /charm/containers/placement-api/pebble.socket
                client.container_name = socket_path.split('/')[3]
                self._pebble_clients[socket_path] = client
            return client

        def network_get(
            self, endpoint_name: str, relation_id: str = None
        ) -> dict:
            """Return a fake set of network data."""
            network_data = {
                "bind-addresses": [
                    {
                        "interface-name": "eth0",
                        "addresses": [
                            {"cidr": "10.0.0.0/24", "value": "10.0.0.10"}
                        ],
                    }
                ],
                "ingress-addresses": ["10.0.0.10"],
                "egress-subnets": ["10.0.0.0/24"],
            }
            return network_data

    filename = inspect.getfile(charm_class)
    charm_dir = pathlib.Path(filename).parents[1]

    if not charm_metadata:
        metadata_file = f"{charm_dir}/metadata.yaml"
        if os.path.isfile(metadata_file):
            with open(metadata_file) as f:
                charm_metadata = f.read()
    if not charm_config:
        config_file = f"{charm_dir}/config.yaml"
        if os.path.isfile(config_file):
            with open(config_file) as f:
                charm_config = f.read()

    harness = Harness(
        charm_class,
        meta=charm_metadata,
        config=charm_config
    )
    harness._backend = _OSTestingModelBackend(
        harness._unit_name, harness._meta
    )
    harness._model = model.Model(harness._meta, harness._backend)
    harness._framework = framework.Framework(
        ":memory:", harness._charm_dir, harness._meta, harness._model
    )
    if initial_charm_config:
        harness.update_config(initial_charm_config)
    else:
        defaults = {
            k: v['default']
            for k, v in yaml.load(charm_config)['options'].items()}
        harness.update_config(defaults)
    return harness
