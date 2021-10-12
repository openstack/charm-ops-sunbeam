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
import sys

sys.path.append('lib')  # noqa
sys.path.append('src')  # noqa

import advanced_sunbeam_openstack.charm as sunbeam_charm
import advanced_sunbeam_openstack.test_utils as test_utils
from . import test_charms


class TestOSBaseOperatorCharm(test_utils.CharmTestCase):

    PATCHES = [
    ]

    def setUp(self):
        self.container_calls = {
            'push': {},
            'pull': [],
            'remove_path': []}
        super().setUp(sunbeam_charm, self.PATCHES)
        self.harness = test_utils.get_harness(
            test_charms.MyCharm,
            test_charms.CHARM_METADATA,
            self.container_calls)
        self.harness.update_config(test_charms.CHARM_CONFIG)
        self.harness.begin()
        self.addCleanup(self.harness.cleanup)

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
        self.assertEqual(
            self.container_calls['push'],
            {})

    def test_handler_prefix(self):
        self.assertEqual(
            self.harness.charm.handler_prefix,
            'my_service')

    def test_container_names(self):
        self.assertEqual(
            self.harness.charm.container_names,
            ['my-service'])

    def test_relation_handlers_ready(self):
        self.assertTrue(
            self.harness.charm.relation_handlers_ready())


class TestOSBaseOperatorAPICharm(test_utils.CharmTestCase):

    PATCHES = [
    ]

    def setUp(self):
        self.container_calls = {
            'push': {},
            'pull': [],
            'remove_path': []}

        super().setUp(sunbeam_charm, self.PATCHES)
        self.harness = test_utils.get_harness(
            test_charms.MyAPICharm,
            test_charms.API_CHARM_METADATA,
            self.container_calls)

        self.addCleanup(self.harness.cleanup)
        self.harness.update_config(test_charms.CHARM_CONFIG)
        self.harness.begin()

    def set_pebble_ready(self):
        self.harness.container_pebble_ready('my-service')

    def test_write_config(self):
        self.harness.set_leader()
        self.set_pebble_ready()
        test_utils.add_api_relations(self.harness)
        expect_entries = [
            '/bin/wsgi_admin',
            'hardpassword',
            'true',
            'rabbit://my-service:rabbit.pass@10.0.0.13:5672/openstack',
            'rabbithost1.local',
            'svcpass1']
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
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
        rel_data = self.harness.get_relation_data(
            db_rel_id,
            'my-service')
        requested_db = json.loads(rel_data['databases'])[0]
        self.assertRegex(requested_db, r'^db_.*my_service$')

    def test_contexts(self):
        self.harness.set_leader()
        self.set_pebble_ready()
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
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
