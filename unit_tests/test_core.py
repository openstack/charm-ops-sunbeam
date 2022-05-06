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

"""Test aso."""

import json
import mock
import sys

sys.path.append('lib')  # noqa
sys.path.append('src')  # noqa

import advanced_sunbeam_openstack.charm as sunbeam_charm
import advanced_sunbeam_openstack.test_utils as test_utils
from . import test_charms


class TestOSBaseOperatorCharm(test_utils.CharmTestCase):
    """Test for the OSBaseOperatorCharm class."""

    PATCHES = [
    ]

    def setUp(self) -> None:
        """Charm test class setup."""
        self.container_calls = test_utils.ContainerCalls()
        super().setUp(sunbeam_charm, self.PATCHES)
        self.harness = test_utils.get_harness(
            test_charms.MyCharm,
            test_charms.CHARM_METADATA,
            self.container_calls,
            charm_config=test_charms.CHARM_CONFIG,
            initial_charm_config=test_charms.INITIAL_CHARM_CONFIG)
        self.harness.begin()
        self.addCleanup(self.harness.cleanup)

    def set_pebble_ready(self) -> None:
        """Set pebble ready event."""
        self.harness.container_pebble_ready('my-service')

    def test_pebble_ready_handler(self) -> None:
        """Test is raised and observed."""
        self.assertEqual(self.harness.charm.seen_events, [])
        self.set_pebble_ready()
        self.assertEqual(self.harness.charm.seen_events, ['PebbleReadyEvent'])

    def test_write_config(self) -> None:
        """Test writing config when charm is ready."""
        self.set_pebble_ready()
        self.assertEqual(
            self.container_calls.push['my-service'],
            [])

    def test_container_names(self) -> None:
        """Test container name list is correct."""
        self.assertEqual(
            self.harness.charm.container_names,
            ['my-service'])

    def test_relation_handlers_ready(self) -> None:
        """Test relation handlers are ready."""
        self.assertTrue(
            self.harness.charm.relation_handlers_ready())


class TestOSBaseOperatorAPICharm(test_utils.CharmTestCase):
    """Test for the OSBaseOperatorAPICharm class."""

    PATCHES = []

    @mock.patch(
        'charms.observability_libs.v0.kubernetes_service_patch.'
        'KubernetesServicePatch')
    def setUp(self, mock_svc_patch: mock.patch) -> None:
        """Charm test class setup."""
        self.container_calls = test_utils.ContainerCalls()

        super().setUp(sunbeam_charm, self.PATCHES)
        self.harness = test_utils.get_harness(
            test_charms.MyAPICharm,
            test_charms.API_CHARM_METADATA,
            self.container_calls,
            charm_config=test_charms.CHARM_CONFIG,
            initial_charm_config=test_charms.INITIAL_CHARM_CONFIG)

        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def set_pebble_ready(self) -> None:
        """Set pebble ready event."""
        self.harness.container_pebble_ready('my-service')

    def test_write_config(self) -> None:
        """Test when charm is ready configs are written correctly."""
        test_utils.add_complete_ingress_relation(self.harness)
        self.harness.set_leader()
        test_utils.add_complete_peer_relation(self.harness)
        self.set_pebble_ready()
        self.harness.charm.leader_set({'foo': 'bar'})
        test_utils.add_api_relations(self.harness)
        test_utils.add_complete_cloud_credentials_relation(self.harness)
        expect_entries = [
            '/bin/wsgi_admin',
            'hardpassword',
            'true',
            'rabbit://my-service:rabbit.pass@10.0.0.13:5672/openstack',
            'rabbithost1.local',
            'svcpass1',
            'bar']
        expect_string = '\n' + '\n'.join(expect_entries)
        self.harness.set_can_connect('my-service', True)
        self.check_file(
            'my-service',
            '/etc/my-service/my-service.conf',
            contents=expect_string,
            user='my-service',
            group='my-service',
        )
        self.check_file(
            'my-service',
            '/etc/apache2/sites-available/wsgi-my-service.conf',
            contents=expect_string,
            user='root',
            group='root',
        )

    def test__on_database_changed(self) -> None:
        """Test database is requested."""
        rel_id = self.harness.add_relation('peers', 'my-service')
        self.harness.add_relation_unit(
            rel_id,
            'my-service/1')
        self.harness.set_leader()
        self.set_pebble_ready()
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
        rel_data = self.harness.get_relation_data(
            db_rel_id,
            'my-service')
        requested_db = json.loads(rel_data['databases'])[0]
        self.assertEqual(requested_db, 'my_service')

    def test_contexts(self) -> None:
        """Test contexts are correctly populated."""
        rel_id = self.harness.add_relation('peers', 'my-service')
        self.harness.add_relation_unit(
            rel_id,
            'my-service/1')
        self.harness.set_leader()
        self.set_pebble_ready()
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
        contexts = self.harness.charm.contexts()
        self.assertEqual(
            contexts.wsgi_config.wsgi_admin_script,
            '/bin/wsgi_admin')
        self.assertEqual(
            contexts.shared_db.database_password,
            'hardpassword')
        self.assertEqual(
            contexts.options.debug,
            'true')

    def test_peer_leader_db(self) -> None:
        """Test interacting with peer app db."""
        rel_id = self.harness.add_relation('peers', 'my-service')
        self.harness.add_relation_unit(
            rel_id,
            'my-service/1')
        self.harness.set_leader()
        self.harness.charm.leader_set({'ready': 'true'})
        self.harness.charm.leader_set({'foo': 'bar'})
        self.harness.charm.leader_set(ginger='biscuit')
        rel_data = self.harness.get_relation_data(rel_id, 'my-service')
        self.assertEqual(
            rel_data,
            {'ready': 'true', 'foo': 'bar', 'ginger': 'biscuit'})
        self.assertEqual(
            self.harness.charm.leader_get('ready'),
            'true')
        self.assertEqual(
            self.harness.charm.leader_get('foo'),
            'bar')
        self.assertEqual(
            self.harness.charm.leader_get('ginger'),
            'biscuit')

    def test_peer_leader_ready(self) -> None:
        """Test peer leader ready methods."""
        rel_id = self.harness.add_relation('peers', 'my-service')
        self.harness.add_relation_unit(
            rel_id,
            'my-service/1')
        self.harness.set_leader()
        self.assertFalse(self.harness.charm.is_leader_ready())
        self.harness.charm.set_leader_ready()
        self.assertTrue(self.harness.charm.is_leader_ready())
