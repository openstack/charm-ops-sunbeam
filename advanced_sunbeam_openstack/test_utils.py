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


import io
import json
from mock import patch
import unittest
import sys

sys.path.append('lib')  # noqa
sys.path.append('src')  # noqa

from ops import framework, model

from ops.testing import Harness, _TestingModelBackend, _TestingPebbleClient


class CharmTestCase(unittest.TestCase):

    def setUp(self, obj, patches):
        super().setUp()
        self.patches = patches
        self.obj = obj
        self.patch_all()

    def patch(self, method):
        _m = patch.object(self.obj, method)
        mock = _m.start()
        self.addCleanup(_m.stop)
        return mock

    def patch_obj(self, obj, method):
        _m = patch.object(obj, method)
        mock = _m.start()
        self.addCleanup(_m.stop)
        return mock

    def patch_all(self):
        for method in self.patches:
            setattr(self, method, self.patch(method))


def add_base_amqp_relation(harness):
    rel_id = harness.add_relation('amqp', 'rabbitmq')
    harness.add_relation_unit(
        rel_id,
        'rabbitmq/0')
    harness.add_relation_unit(
        rel_id,
        'rabbitmq/0')
    harness.update_relation_data(
        rel_id,
        'rabbitmq/0',
        {'ingress-address': '10.0.0.13'})
    return rel_id


def add_amqp_relation_credentials(harness, rel_id):
    harness.update_relation_data(
        rel_id,
        'rabbitmq',
        {
            'hostname': 'rabbithost1.local',
            'password': 'rabbit.pass'})


def add_base_identity_service_relation(harness):
    rel_id = harness.add_relation('identity-service', 'keystone')
    harness.add_relation_unit(
        rel_id,
        'keystone/0')
    harness.add_relation_unit(
        rel_id,
        'keystone/0')
    harness.update_relation_data(
        rel_id,
        'keystone/0',
        {'ingress-address': '10.0.0.33'})
    return rel_id


def add_identity_service_relation_response(harness, rel_id):
    harness.update_relation_data(
        rel_id,
        'keystone',
        {
            'admin-domain-id': 'admindomid1',
            'admin-project-id': 'adminprojid1',
            'admin-user-id': 'adminuserid1',
            'api-version': '3',
            'auth-host': 'keystone.local',
            'auth-port': '12345',
            'auth-protocol': 'http',
            'internal-host': 'keystone.internal',
            'internal-port': '5000',
            'internal-protocol': 'http',
            'service-domain': 'servicedom',
            'service-domain_id': 'svcdomid1',
            'service-host': 'keystone.service',
            'service-password': 'svcpass1',
            'service-port': '5000',
            'service-protocol': 'http',
            'service-project': 'svcproj1',
            'service-project-id': 'svcprojid1',
            'service-username': 'svcuser1'})


def add_base_db_relation(harness):
    rel_id = harness.add_relation('my-service-db', 'mysql')
    harness.add_relation_unit(
        rel_id,
        'mysql/0')
    harness.add_relation_unit(
        rel_id,
        'mysql/0')
    harness.update_relation_data(
        rel_id,
        'mysql/0',
        {'ingress-address': '10.0.0.3'})
    return rel_id


def add_db_relation_credentials(harness, rel_id):
    harness.update_relation_data(
        rel_id,
        'mysql',
        {
            'databases': json.dumps(['db1']),
            'data': json.dumps({
                'credentials': {
                    'username': 'foo',
                    'password': 'hardpassword',
                    'address': '10.0.0.10'}})})


def add_api_relations(harness):
        add_db_relation_credentials(
            harness,
            add_base_db_relation(harness))
        add_amqp_relation_credentials(
            harness,
            add_base_amqp_relation(harness))
        add_identity_service_relation_response(
            harness,
            add_base_identity_service_relation(harness))


def get_harness(charm_class, charm_meta, container_calls):

    class _OSTestingPebbleClient(_TestingPebbleClient):

        def push(
                self, path, source, *,
                encoding='utf-8', make_dirs=False, permissions=None,
                user_id=None, user=None, group_id=None, group=None):
            container_calls['push'][path] = {
                'source': source,
                'permissions': permissions,
                'user': user,
                'group': group}

        def pull(self, path, *, encoding='utf-8'):
            container_calls['pull'].append(path)
            reader = io.StringIO("0")
            return reader

        def remove_path(self, path, *, recursive=False):
            container_calls['remove_path'].append(path)

    class _OSTestingModelBackend(_TestingModelBackend):

        def get_pebble(self, socket_path: str):
            client = self._pebble_clients.get(socket_path, None)
            if client is None:
                client = _OSTestingPebbleClient(self)
                self._pebble_clients[socket_path] = client
            return client

    harness = Harness(
        charm_class,
        meta=charm_meta,
    )
    harness._backend = _OSTestingModelBackend(
        harness._unit_name, harness._meta)
    harness._model = model.Model(
        harness._meta,
        harness._backend)
    harness._framework = framework.Framework(
        ":memory:",
        harness._charm_dir,
        harness._meta,
        harness._model)
    # END Workaround
    return harness
