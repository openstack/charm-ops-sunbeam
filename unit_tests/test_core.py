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

import json
from mock import patch
import unittest
import sys

sys.path.append('lib')  # noqa
sys.path.append('src')  # noqa

from ops.testing import Harness

import advanced_sunbeam_openstack.core as core

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

requires:
  my-service-db:
    interface: mysql_datastore
    limit: 1
  ingress:
    interface: ingress


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

    def patch_all(self):
        for method in self.patches:
            setattr(self, method, self.patch(method))


class MyCharm(core.OSBaseOperatorCharm):

    openstack_release = 'diablo'
    service_name = 'my-service'

    def __init__(self, framework):
        super().__init__(framework)
        self.seen_events = []
        self.render_calls = []

    def renderer(self, containers, container_configs, template_dir,
                 openstack_release, adapters):
        self.render_calls.append(
            (
                containers,
                container_configs,
                template_dir,
                openstack_release,
                adapters))

    def _log_event(self, event):
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(self, event):
        self._log_event(event)

    def _on_config_changed(self, event):
        self._log_event(event)

    @property
    def public_ingress_port(self):
        return 789


class TestOSBaseOperatorCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(
            MyCharm,
            meta=CHARM_METADATA
        )

        self.addCleanup(self.harness.cleanup)
        self.harness.update_config(CHARM_CONFIG)
        self.harness.begin()

    def set_pebble_ready(self):
        container = self.harness.model.unit.get_container("my-service")
        # Emit the PebbleReadyEvent
        self.harness.charm.on.my_service_pebble_ready.emit(container)

    def test_pebble_ready_handler(self):
        self.assertEqual(self.harness.charm.seen_events, [])
        self.set_pebble_ready()
        self.assertEqual(self.harness.charm.seen_events, ['PebbleReadyEvent'])

    def test_write_config(self):
        self.set_pebble_ready()
        self.harness.charm.write_config()
        self.assertEqual(
            self.harness.charm.render_calls[0],
            (
                [self.harness.model.unit.get_container("my-service")],
                [],
                'src/templates',
                'diablo',
                self.harness.charm.adapters))

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


class MyAPICharm(core.OSBaseOperatorAPICharm):
    openstack_release = 'diablo'
    service_name = 'my-service'
    wsgi_admin_script = '/bin/wsgi_admin'
    wsgi_public_script = '/bin/wsgi_public'

    def __init__(self, framework):
        self.seen_events = []
        self.render_calls = []
        super().__init__(framework)

    def renderer(self, containers, container_configs, template_dir,
                 openstack_release, adapters):
        self.render_calls.append(
            (
                containers,
                container_configs,
                template_dir,
                openstack_release,
                adapters))

    def _log_event(self, event):
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(self, event):
        super()._on_service_pebble_ready(event)
        self._log_event(event)

    def _on_config_changed(self, event):
        self._log_event(event)

    @property
    def public_ingress_port(self):
        return 789


class TestOSBaseOperatorAPICharm(CharmTestCase):

    PATCHES = [
        'sunbeam_cprocess',
    ]

    def setUp(self):
        super().setUp(core, self.PATCHES)
        self.sunbeam_cprocess.ContainerProcessError = Exception
        self.harness = Harness(
            MyAPICharm,
            meta=CHARM_METADATA
        )

        self.addCleanup(self.harness.cleanup)
        self.harness.update_config(CHARM_CONFIG)
        self.harness.begin()

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
        self.set_pebble_ready()
        self.harness.charm.write_config()
        self.assertEqual(
            self.harness.charm.render_calls[0],
            (
                [self.harness.model.unit.get_container("my-service")],
                [
                    core.ContainerConfigFile(
                        container_names=['my-service'],
                        path=('/etc/apache2/sites-available/'
                              'wsgi-my-service.conf'),
                        user='root',
                        group='root')],
                'src/templates',
                'diablo',
                self.harness.charm.adapters))

    def test__on_database_changed(self):
        self.harness.set_leader()
        self.set_pebble_ready()
        rel_id = self.add_base_db_relation()
        rel_data = self.harness.get_relation_data(
            rel_id,
            'my-service')
        requested_db = json.loads(rel_data['databases'])[0]
        self.assertRegex(requested_db, r'^db_.*my_service$')

    def test_DBAdapter(self):
        self.harness.set_leader()
        self.set_pebble_ready()
        rel_id = self.add_base_db_relation()
        self.add_db_relation_credentials(rel_id)
        self.assertEqual(
            self.harness.charm.adapters.wsgi_config.wsgi_admin_script,
            '/bin/wsgi_admin')
        self.assertEqual(
            self.harness.charm.adapters.my_service_db.database_password,
            'hardpassword')
        self.assertEqual(
            self.harness.charm.adapters.options.debug,
            'true')
