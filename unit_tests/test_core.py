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
import os
import tempfile
from mock import ANY, patch
import unittest
import sys

sys.path.append('lib')  # noqa
sys.path.append('src')  # noqa

from ops import framework, model

from ops.testing import Harness, _TestingModelBackend, _TestingPebbleClient

import advanced_sunbeam_openstack.charm as sunbeam_charm

CHARM_CONFIG = {
    'debug': 'true'}

CHARM_METADATA = '''
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
'''

API_CHARM_METADATA = '''
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
  my-service-db:
    interface: mysql_datastore
    limit: 1
  ingress:
    interface: ingress
  amqp:
    interface: rabbitmq

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
'''


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


class MyCharm(sunbeam_charm.OSBaseOperatorCharm):

    openstack_release = 'diablo'
    service_name = 'my-service'

    def __init__(self, framework):
        super().__init__(framework)
        self.seen_events = []
        self.render_calls = []

    def _log_event(self, event):
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(self, event):
        super()._on_service_pebble_ready(event)
        self._log_event(event)

    def _on_config_changed(self, event):
        self._log_event(event)

    def configure_charm(self, event):
        super().configure_charm(event)
        self._log_event(event)

    @property
    def public_ingress_port(self):
        return 789


class TestOSBaseOperatorCharm(CharmTestCase):

    PATCHES = [
    ]

    def setUp(self):
        super().setUp(sunbeam_charm, self.PATCHES)
        self.harness = Harness(
            MyCharm,
            meta=CHARM_METADATA
        )
        self.harness.update_config(CHARM_CONFIG)
        self.harness.begin()
        self.addCleanup(self.harness.cleanup)

    def set_pebble_ready(self):
        container = self.harness.model.unit.get_container("my-service")
        # Emit the PebbleReadyEvent
        self.harness.charm.on.my_service_pebble_ready.emit(container)

    @patch('advanced_sunbeam_openstack.templating.sidecar_config_render')
    def test_pebble_ready_handler(self, _renderer):
        self.assertEqual(self.harness.charm.seen_events, [])
        self.set_pebble_ready()
        self.assertEqual(self.harness.charm.seen_events, ['PebbleReadyEvent'])

    @patch('advanced_sunbeam_openstack.templating.sidecar_config_render')
    def test_write_config(self, _renderer):
        self.set_pebble_ready()
        _renderer.assert_called_once_with(
            [self.harness.model.unit.get_container("my-service")],
            [],
            'src/templates',
            'diablo',
            ANY)

    def test_handler_prefix(self):
        self.assertEqual(
            self.harness.charm.handler_prefix,
            'my_service')

    def test_container_names(self):
        self.assertEqual(
            self.harness.charm.container_names,
            ['my-service'])

    def test_template_dir(self):
        self.assertEqual(
            self.harness.charm.template_dir,
            'src/templates')

    def test_relation_handlers_ready(self):
        self.assertTrue(
            self.harness.charm.relation_handlers_ready())

TEMPLATE_CONTENTS = """
{{ wsgi_config.wsgi_admin_script }}
{{ my_service_db.database_password }}
{{ options.debug }}
{{ amqp.transport_url }}
"""


class MyAPICharm(sunbeam_charm.OSBaseOperatorAPICharm):
    openstack_release = 'diablo'
    service_name = 'my-service'
    wsgi_admin_script = '/bin/wsgi_admin'
    wsgi_public_script = '/bin/wsgi_public'

    def __init__(self, framework):
        self.seen_events = []
        self.render_calls = []
        self._template_dir = self._setup_templates()
        super().__init__(framework)

    def _setup_templates(self):
        tmpdir = tempfile.mkdtemp()
        _template_dir = f'{tmpdir}/templates'
        os.mkdir(_template_dir)
        with open(f'{_template_dir}/my-service.conf.j2', 'w') as f:
            f.write(TEMPLATE_CONTENTS)
        with open(f'{_template_dir}/wsgi-my-service.conf.j2', 'w') as f:
            f.write(TEMPLATE_CONTENTS)
        return _template_dir

    def _log_event(self, event):
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(self, event):
        super()._on_service_pebble_ready(event)
        self._log_event(event)

    def _on_config_changed(self, event):
        self._log_event(event)

    @property
    def default_public_ingress_port(self):
        return 789

    @property
    def template_dir(self):
        return self._template_dir


class TestOSBaseOperatorAPICharm(CharmTestCase):

    PATCHES = [
    ]

    def setUp(self):
        container_calls = {
            'push': {},
            'pull': [],
            'remove_path': []}

        super().setUp(sunbeam_charm, self.PATCHES)

        class _LYTestingPebbleClient(_TestingPebbleClient):

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

        class _LYTestingModelBackend(_TestingModelBackend):

            def get_pebble(self, socket_path: str):
                client = self._pebble_clients.get(socket_path, None)
                if client is None:
                    client = _LYTestingPebbleClient(self)
                    self._pebble_clients[socket_path] = client
                return client

        self.container_calls = container_calls
        # self.sunbeam_cprocess.ContainerProcessError = Exception
        self.harness = Harness(
            MyAPICharm,
            meta=API_CHARM_METADATA
        )
        self.harness._backend = _LYTestingModelBackend(
            self.harness._unit_name, self.harness._meta)
        self.harness._model = model.Model(
            self.harness._meta,
            self.harness._backend)
        self.harness._framework = framework.Framework(
            ":memory:",
            self.harness._charm_dir,
            self.harness._meta,
            self.harness._model)
        # END Workaround

        self.addCleanup(self.harness.cleanup)
        self.harness.update_config(CHARM_CONFIG)
        self.harness.begin()

    def add_base_amqp_relation(self):
        rel_id = self.harness.add_relation('amqp', 'rabbitmq')
        self.harness.add_relation_unit(
            rel_id,
            'rabbitmq/0')
        self.harness.add_relation_unit(
            rel_id,
            'rabbitmq/0')
        self.harness.update_relation_data(
            rel_id,
            'rabbitmq/0',
            {'ingress-address': '10.0.0.13'})
        return rel_id

    def add_amqp_relation_credentials(self, rel_id):
        self.harness.update_relation_data(
            rel_id,
            'rabbitmq',
            {
                'hostname': 'rabbithost1.local',
                'password': 'rabbit.pass'})

    def add_base_db_relation(self):
        rel_id = self.harness.add_relation('my-service-db', 'mysql')
        self.harness.add_relation_unit(
            rel_id,
            'mysql/0')
        self.harness.add_relation_unit(
            rel_id,
            'mysql/0')
        self.harness.update_relation_data(
            rel_id,
            'mysql/0',
            {'ingress-address': '10.0.0.3'})
        return rel_id

    def add_db_relation_credentials(self, rel_id):
        self.harness.update_relation_data(
            rel_id,
            'mysql',
            {
                'databases': json.dumps(['db1']),
                'data': json.dumps({
                    'credentials': {
                        'username': 'foo',
                        'password': 'hardpassword',
                        'address': '10.0.0.10'}})})

    def set_pebble_ready(self):
        self.harness.container_pebble_ready('my-service')

    def test_write_config(self):
        self.harness.set_leader()
        self.set_pebble_ready()
        db_rel_id = self.add_base_db_relation()
        self.add_db_relation_credentials(db_rel_id)
        amqp_rel_id = self.add_base_amqp_relation()
        self.add_amqp_relation_credentials(amqp_rel_id)
        expect_entries = [
            '/bin/wsgi_admin',
            'hardpassword',
            'true',
            'rabbit://my-service:rabbit.pass@10.0.0.13:5672/my-service']
        expect_string = '\n' + '\n'.join(expect_entries)
        self.assertEqual(
            self.container_calls['push']['/etc/my-service/my-service.conf'],
            {
                'group': 'my-service',
                'permissions': None,
                'source': expect_string,
                'user': 'my-service'})
        self.assertEqual(
            self.container_calls['push'][
                '/etc/apache2/sites-available/wsgi-my-service.conf'],
            {
                'group': 'root',
                'permissions': None,
                'source': expect_string,
                'user': 'root'})

    @patch('advanced_sunbeam_openstack.templating.sidecar_config_render')
    def test__on_database_changed(self, _renderer):
        self.harness.set_leader()
        self.set_pebble_ready()
        rel_id = self.add_base_db_relation()
        self.add_db_relation_credentials(rel_id)
        rel_data = self.harness.get_relation_data(
            rel_id,
            'my-service')
        requested_db = json.loads(rel_data['databases'])[0]
        self.assertRegex(requested_db, r'^db_.*my_service$')

    def test_contexts(self):
        self.harness.set_leader()
        self.set_pebble_ready()
        rel_id = self.add_base_db_relation()
        self.add_db_relation_credentials(rel_id)
        contexts = self.harness.charm.contexts()
        self.assertEqual(
            contexts.wsgi_config.wsgi_admin_script,
            '/bin/wsgi_admin')
        self.assertEqual(
            contexts.my_service_db.database_password,
            'hardpassword')
        self.assertEqual(
            contexts.options.debug,
            'true')
