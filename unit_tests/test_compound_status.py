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

"""Test compound_status."""

import sys

import mock

sys.path.append("lib")  # noqa
sys.path.append("src")  # noqa

from ops.model import (
    ActiveStatus,
    BlockedStatus,
    UnknownStatus,
    WaitingStatus,
)

import ops_sunbeam.charm as sunbeam_charm
import ops_sunbeam.compound_status as compound_status
import ops_sunbeam.test_utils as test_utils

from . import (
    test_charms,
)


class TestCompoundStatus(test_utils.CharmTestCase):
    """Test for the compound_status module."""

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
        self.harness.begin()
        self.addCleanup(self.harness.cleanup)

    def test_status_triggering_on_set(self) -> None:
        """Updating a status should call the on_update function if set."""
        status = compound_status.Status("test")

        # this shouldn't fail, even though it's not connected to a pool yet,
        # and thus has no on_update set.
        status.set(WaitingStatus("test"))

        # manually set the on_update hook and verify it is called
        on_update_mock = mock.Mock()
        status.on_update = on_update_mock
        status.set(ActiveStatus("test"))
        on_update_mock.assert_called_once_with()

    def test_status_new_unknown_message(self) -> None:
        """New status should be unknown status and empty message."""
        status = compound_status.Status("test")
        self.assertIsInstance(status.status, UnknownStatus)
        self.assertEqual(status.message(), "")

    def test_serializing_status(self) -> None:
        """Serialising a status should work as expected."""
        status = compound_status.Status("mylabel")
        self.assertEqual(
            status._serialize(),
            {
                "status": "unknown",
                "message": "",
            },
        )

        # now with a message and new status
        status.set(WaitingStatus("still waiting..."))
        self.assertEqual(
            status._serialize(),
            {
                "status": "waiting",
                "message": "still waiting...",
            },
        )

        # with a custom priority
        status = compound_status.Status("mylabel", priority=12)
        self.assertEqual(
            status._serialize(),
            {
                "status": "unknown",
                "message": "",
            },
        )

    def test_status_pool_priority(self) -> None:
        """A status pool should display the highest priority status."""
        pool = self.harness.charm.status_pool

        status1 = compound_status.Status("test1")
        pool.add(status1)
        status2 = compound_status.Status("test2", priority=100)
        pool.add(status2)
        status3 = compound_status.Status("test3", priority=30)
        pool.add(status3)

        status1.set(WaitingStatus(""))
        status2.set(WaitingStatus(""))
        status3.set(WaitingStatus(""))

        # status2 has highest priority
        self.assertEqual(
            self.harness.charm.unit.status, WaitingStatus("(test2)")
        )

        # status3 will new be displayed,
        # since blocked is more severe than waiting
        status3.set(BlockedStatus(":("))
        self.assertEqual(
            self.harness.charm.unit.status, BlockedStatus("(test3) :(")
        )

    def test_add_status_idempotency(self) -> None:
        """Should not be issues if add same status twice."""
        pool = self.harness.charm.status_pool

        status1 = compound_status.Status("test1", priority=200)
        pool.add(status1)

        status1.set(WaitingStatus("test"))
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("(test1) test"),
        )

        new_status1 = compound_status.Status("test1", priority=201)
        new_status1.set(BlockedStatus(""))
        pool.add(new_status1)

        # should be the new object in the pool
        self.assertIs(new_status1, pool._pool["test1"])
        self.assertEqual(new_status1.priority(), (1, -201))
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("(test1)"),
        )

    def test_all_active_status(self) -> None:
        """Should not be issues if add same status twice."""
        pool = self.harness.charm.status_pool
        self.harness.charm.bootstrap_status.set(ActiveStatus())

        status1 = compound_status.Status("test1")
        pool.add(status1)
        status2 = compound_status.Status("test2", priority=150)
        pool.add(status2)
        status3 = compound_status.Status("test3", priority=30)
        pool.add(status3)

        status1.set(ActiveStatus(""))
        status2.set(ActiveStatus(""))
        status3.set(ActiveStatus(""))

        # also need to manually activate other default statuses
        pool._pool["container:my-service"].set(ActiveStatus(""))

        # all empty messages should end up as an empty unit status
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus(""))

        # if there's a message (on the highest priority status),
        # it should also show the status prefix
        status2.set(ActiveStatus("a message"))
        self.assertEqual(
            self.harness.charm.unit.status, ActiveStatus("(test2) a message")
        )
