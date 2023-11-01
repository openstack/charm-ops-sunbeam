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

import os
import sys

import mock

sys.path.append("tests/lib")  # noqa
sys.path.append("src")  # noqa

import ops.model

import ops_sunbeam.charm as sunbeam_charm
import ops_sunbeam.test_utils as test_utils

from . import (
    test_charms,
)


class TestOSBaseOperatorCharm(test_utils.CharmTestCase):
    """Test for the OSBaseOperatorCharm class."""

    PATCHES = []

    def setUp(self) -> None:
        """Charm test class setup."""
        self.container_calls = test_utils.ContainerCalls()
        super().setUp(sunbeam_charm, self.PATCHES)
        self.mock_event = mock.MagicMock()
        self.harness = test_utils.get_harness(
            test_charms.MyCharm,
            test_charms.CHARM_METADATA,
            self.container_calls,
            charm_config=test_charms.CHARM_CONFIG,
            initial_charm_config=test_charms.INITIAL_CHARM_CONFIG,
        )
        self.harness.begin()
        self.addCleanup(self.harness.cleanup)

    def test_write_config(self) -> None:
        """Test writing config when charm is ready."""
        self.assertEqual(self.container_calls.push["my-service"], [])

    def test_relation_handlers_ready(self) -> None:
        """Test relation handlers are ready."""
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            set(),
        )


class TestOSBaseOperatorCharmK8S(test_utils.CharmTestCase):
    """Test for the OSBaseOperatorCharm class."""

    PATCHES = []

    def setUp(self) -> None:
        """Charm test class setup."""
        self.container_calls = test_utils.ContainerCalls()
        super().setUp(sunbeam_charm, self.PATCHES)
        self.harness = test_utils.get_harness(
            test_charms.MyCharmK8S,
            test_charms.CHARM_METADATA_K8S,
            self.container_calls,
            charm_config=test_charms.CHARM_CONFIG,
            initial_charm_config=test_charms.INITIAL_CHARM_CONFIG,
        )
        self.mock_event = mock.MagicMock()
        self.harness.begin()
        self.addCleanup(self.harness.cleanup)

    def set_pebble_ready(self) -> None:
        """Set pebble ready event."""
        self.harness.container_pebble_ready("my-service")

    def test_pebble_ready_handler(self) -> None:
        """Test is raised and observed."""
        self.assertEqual(self.harness.charm.seen_events, [])
        self.set_pebble_ready()
        self.assertEqual(self.harness.charm.seen_events, ["PebbleReadyEvent"])

    def test_write_config(self) -> None:
        """Test writing config when charm is ready."""
        self.set_pebble_ready()
        self.assertEqual(self.container_calls.push["my-service"], [])

    def test_container_names(self) -> None:
        """Test container name list is correct."""
        self.assertEqual(self.harness.charm.container_names, ["my-service"])

    def test_relation_handlers_ready(self) -> None:
        """Test relation handlers are ready."""
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            set(),
        )


class _TestOSBaseOperatorAPICharm(test_utils.CharmTestCase):
    """Test for the OSBaseOperatorAPICharm class."""

    PATCHES = []

    def setUp(self, charm_to_test: test_charms.MyAPICharm) -> None:
        """Charm test class setup."""
        self.container_calls = test_utils.ContainerCalls()

        super().setUp(sunbeam_charm, self.PATCHES)
        self.mock_event = mock.MagicMock()
        self.harness = test_utils.get_harness(
            charm_to_test,
            test_charms.API_CHARM_METADATA,
            self.container_calls,
            charm_config=test_charms.CHARM_CONFIG,
            initial_charm_config=test_charms.INITIAL_CHARM_CONFIG,
        )

        # clean up events that were dynamically defined,
        # otherwise we get issues because they'll be redefined,
        # which is not allowed.
        from charms.data_platform_libs.v0.database_requires import (
            DatabaseEvents,
        )

        for attr in (
            "database_database_created",
            "database_endpoints_changed",
            "database_read_only_endpoints_changed",
        ):
            try:
                delattr(DatabaseEvents, attr)
            except AttributeError:
                pass

        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def set_pebble_ready(self) -> None:
        """Set pebble ready event."""
        self.harness.container_pebble_ready("my-service")


class TestOSBaseOperatorAPICharm(_TestOSBaseOperatorAPICharm):
    """Test Charm with services."""

    def setUp(self) -> None:
        """Run test class setup."""
        super().setUp(test_charms.MyAPICharm)

    def test_write_config(self) -> None:
        """Test when charm is ready configs are written correctly."""
        test_utils.add_complete_ingress_relation(self.harness)
        self.harness.set_leader()
        test_utils.add_complete_peer_relation(self.harness)
        self.set_pebble_ready()
        self.harness.charm.leader_set({"foo": "bar"})
        test_utils.add_api_relations(self.harness)
        test_utils.add_complete_identity_credentials_relation(self.harness)
        expect_entries = [
            "/bin/wsgi_admin",
            "hardpassword",
            "True",
            "rabbit://my-service:rabbit.pass@10.0.0.13:5672/openstack",
            "rabbithost1.local",
            "svcpass1",
            "bar",
        ]
        expect_string = "\n" + "\n".join(expect_entries)
        self.harness.set_can_connect("my-service", True)
        effective_user_id = os.geteuid()
        effective_group_id = os.getegid()
        self.check_file(
            "my-service",
            "/etc/my-service/my-service.conf",
            contents=expect_string,
            user=effective_user_id,
            group=effective_group_id,
        )
        self.check_file(
            "my-service",
            "/etc/apache2/sites-available/wsgi-my-service.conf",
            contents=expect_string,
            user=effective_user_id,
            group=effective_group_id,
        )

    def test_assess_status(self) -> None:
        """Test charm is setting status correctly."""
        test_utils.add_complete_ingress_relation(self.harness)
        self.harness.set_leader()
        test_utils.add_complete_peer_relation(self.harness)
        self.harness.charm.leader_set({"foo": "bar"})
        test_utils.add_api_relations(self.harness)
        test_utils.add_complete_identity_credentials_relation(self.harness)
        self.harness.set_can_connect("my-service", True)
        self.assertNotEqual(
            self.harness.charm.status.status, ops.model.ActiveStatus()
        )
        self.set_pebble_ready()
        for ph in self.harness.charm.pebble_handlers:
            self.assertTrue(ph.service_ready)

        self.assertEqual(
            self.harness.charm.status.status, ops.model.ActiveStatus()
        )

    def test_start_services(self) -> None:
        """Test service is started."""
        test_utils.add_complete_ingress_relation(self.harness)
        self.harness.set_leader()
        test_utils.add_complete_peer_relation(self.harness)
        self.set_pebble_ready()
        self.harness.charm.leader_set({"foo": "bar"})
        test_utils.add_api_relations(self.harness)
        test_utils.add_complete_identity_credentials_relation(self.harness)
        self.harness.set_can_connect("my-service", True)
        self.assertEqual(
            self.container_calls.started_services("my-service"),
            ["wsgi-my-service"],
        )

    def test__on_database_changed(self) -> None:
        """Test database is requested."""
        rel_id = self.harness.add_relation("peers", "my-service")
        self.harness.add_relation_unit(rel_id, "my-service/1")
        self.harness.set_leader()
        self.set_pebble_ready()
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
        rel_data = self.harness.get_relation_data(db_rel_id, "my-service")
        requested_db = rel_data["database"]
        self.assertEqual(requested_db, "my_service")

    def test_contexts(self) -> None:
        """Test contexts are correctly populated."""
        rel_id = self.harness.add_relation("peers", "my-service")
        self.harness.add_relation_unit(rel_id, "my-service/1")
        self.harness.set_leader()
        self.set_pebble_ready()
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
        contexts = self.harness.charm.contexts()
        self.assertEqual(
            contexts.wsgi_config.wsgi_admin_script, "/bin/wsgi_admin"
        )
        self.assertEqual(contexts.database.database_password, "hardpassword")
        self.assertEqual(contexts.options.debug, True)

    def test_peer_leader_db(self) -> None:
        """Test interacting with peer app db."""
        rel_id = self.harness.add_relation("peers", "my-service")
        self.harness.add_relation_unit(rel_id, "my-service/1")
        self.harness.set_leader()
        self.harness.charm.leader_set({"ready": "true"})
        self.harness.charm.leader_set({"foo": "bar"})
        self.harness.charm.leader_set(ginger="biscuit")
        rel_data = self.harness.get_relation_data(rel_id, "my-service")
        self.assertEqual(
            rel_data, {"ready": "true", "foo": "bar", "ginger": "biscuit"}
        )
        self.assertEqual(self.harness.charm.leader_get("ready"), "true")
        self.assertEqual(self.harness.charm.leader_get("foo"), "bar")
        self.assertEqual(self.harness.charm.leader_get("ginger"), "biscuit")

    def test_peer_unit_data(self) -> None:
        """Test interacting with peer app db."""
        rel_id = self.harness.add_relation("peers", "my-service")
        self.harness.add_relation_unit(rel_id, "my-service/1")
        self.harness.update_relation_data(
            rel_id, "my-service/1", {"today": "monday"}
        )
        self.assertEqual(
            self.harness.charm.peers.get_all_unit_values(
                "today",
                include_local_unit=False,
            ),
            ["monday"],
        )
        self.assertEqual(
            self.harness.charm.peers.get_all_unit_values(
                "today",
                include_local_unit=True,
            ),
            ["monday"],
        )
        self.harness.charm.peers.set_unit_data({"today": "friday"})
        self.assertEqual(
            self.harness.charm.peers.get_all_unit_values(
                "today",
                include_local_unit=False,
            ),
            ["monday"],
        )
        self.assertEqual(
            self.harness.charm.peers.get_all_unit_values(
                "today",
                include_local_unit=True,
            ),
            ["monday", "friday"],
        )

    def test_peer_leader_ready(self) -> None:
        """Test peer leader ready methods."""
        rel_id = self.harness.add_relation("peers", "my-service")
        self.harness.add_relation_unit(rel_id, "my-service/1")
        self.harness.set_leader()
        self.assertFalse(self.harness.charm.is_leader_ready())
        self.harness.charm.set_leader_ready()
        self.assertTrue(self.harness.charm.is_leader_ready())

    def test_endpoint_urls(self) -> None:
        """Test public_url and internal_url properties."""
        # Add ingress relation
        test_utils.add_complete_ingress_relation(self.harness)
        self.assertEqual(
            self.harness.charm.internal_url, "http://internal-url:80"
        )
        self.assertEqual(self.harness.charm.public_url, "http://public-url:80")

    @mock.patch("ops_sunbeam.charm.Client")
    def test_endpoint_urls_no_ingress(self, mock_client: mock.patch) -> None:
        """Test public_url and internal_url with no ingress defined."""

        class MockService:
            """Mock lightkube client service object."""

            def __init__(self) -> None:
                self.status = None

        mock_client.return_value = mock.MagicMock()
        mock_client.return_value.get.return_value = MockService()
        self.assertEqual(
            self.harness.charm.internal_url, "http://10.0.0.10:789"
        )
        self.assertEqual(self.harness.charm.public_url, "http://10.0.0.10:789")

    def test_relation_handlers_ready(self) -> None:
        """Test relation handlers are ready."""
        # Add all mandatory relations and test relation_handlers_ready
        db_rel_id = test_utils.add_base_db_relation(self.harness)
        test_utils.add_db_relation_credentials(self.harness, db_rel_id)
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            {"identity-service", "ingress-public", "amqp"},
        )

        amqp_rel_id = test_utils.add_base_amqp_relation(self.harness)
        test_utils.add_amqp_relation_credentials(self.harness, amqp_rel_id)
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            {"ingress-public", "identity-service"},
        )

        identity_rel_id = test_utils.add_base_identity_service_relation(
            self.harness
        )
        test_utils.add_identity_service_relation_response(
            self.harness, identity_rel_id
        )
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            {"ingress-public"},
        )

        ingress_rel_id = test_utils.add_ingress_relation(
            self.harness, "public"
        )
        test_utils.add_ingress_relation_data(
            self.harness, ingress_rel_id, "public"
        )

        ceph_access_rel_id = test_utils.add_base_ceph_access_relation(
            self.harness
        )
        test_utils.add_ceph_access_relation_response(
            self.harness, ceph_access_rel_id
        )
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            set(),
        )

        # Add an optional relation and test if relation_handlers_ready
        # returns True
        optional_rel_id = test_utils.add_ingress_relation(
            self.harness, "internal"
        )
        test_utils.add_ingress_relation_data(
            self.harness, optional_rel_id, "internal"
        )
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            set(),
        )

        # Remove a mandatory relation and test if relation_handlers_ready
        # returns False
        self.harness.remove_relation(ingress_rel_id)
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            {"ingress-public"},
        )

        # Add the mandatory relation back and retest relation_handlers_ready
        ingress_rel_id = test_utils.add_ingress_relation(
            self.harness, "public"
        )
        test_utils.add_ingress_relation_data(
            self.harness, ingress_rel_id, "public"
        )
        self.assertSetEqual(
            self.harness.charm.get_mandatory_relations_not_ready(
                self.mock_event
            ),
            set(),
        )

    def test_add_explicit_port(self):
        """Test add_explicit_port method."""
        self.assertEqual(
            self.harness.charm.add_explicit_port("http://test.org/something"),
            "http://test.org:80/something",
        )
        self.assertEqual(
            self.harness.charm.add_explicit_port(
                "http://test.org:80/something"
            ),
            "http://test.org:80/something",
        )
        self.assertEqual(
            self.harness.charm.add_explicit_port("https://test.org/something"),
            "https://test.org:443/something",
        )
        self.assertEqual(
            self.harness.charm.add_explicit_port(
                "https://test.org:443/something"
            ),
            "https://test.org:443/something",
        )
        self.assertEqual(
            self.harness.charm.add_explicit_port(
                "http://test.org:8080/something"
            ),
            "http://test.org:8080/something",
        )
        self.assertEqual(
            self.harness.charm.add_explicit_port(
                "https://test.org:8443/something"
            ),
            "https://test.org:8443/something",
        )


class TestOSBaseOperatorMultiSVCAPICharm(_TestOSBaseOperatorAPICharm):
    """Test Charm with multiple services."""

    def setUp(self) -> None:
        """Charm test class setip."""
        super().setUp(test_charms.TestMultiSvcCharm)

    def test_start_services(self) -> None:
        """Test multiple services are started."""
        test_utils.add_complete_ingress_relation(self.harness)
        self.harness.set_leader()
        test_utils.add_complete_peer_relation(self.harness)
        self.set_pebble_ready()
        self.harness.charm.leader_set({"foo": "bar"})
        test_utils.add_api_relations(self.harness)
        test_utils.add_complete_identity_credentials_relation(self.harness)
        self.harness.set_can_connect("my-service", True)
        self.assertEqual(
            sorted(self.container_calls.started_services("my-service")),
            sorted(["apache forwarder", "my-service"]),
        )
