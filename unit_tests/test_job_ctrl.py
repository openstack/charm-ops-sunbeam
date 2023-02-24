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

"""Test job ctrl code."""

import sys

import mock

sys.path.append("lib")  # noqa
sys.path.append("src")  # noqa

import ops_sunbeam.job_ctrl as sunbeam_job_ctrl
import ops_sunbeam.test_utils as test_utils

from . import (
    test_charms,
)


class JobCtrlCharm(test_charms.MyAPICharm):
    """Test charm that use job ctrl code."""

    unit_job_counter = 1

    @sunbeam_job_ctrl.run_once_per_unit("unit-job")
    def unit_specific_job(self):
        """Run a dummy once per unit job."""
        self.unit_job_counter = self.unit_job_counter + 1


class TestJobCtrl(test_utils.CharmTestCase):
    """Test for the OSBaseOperatorCharm class."""

    PATCHES = ["time"]

    @mock.patch(
        "charms.observability_libs.v0.kubernetes_service_patch."
        "KubernetesServicePatch"
    )
    def setUp(self, mock_svc_patch: mock.patch) -> None:
        """Charm test class setup."""
        self.container_calls = test_utils.ContainerCalls()
        super().setUp(sunbeam_job_ctrl, self.PATCHES)
        self.harness = test_utils.get_harness(
            JobCtrlCharm,
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

    def test_local_job_storage(self) -> None:
        """Test local job storage."""
        local_job_storage = sunbeam_job_ctrl.LocalJobStorage(
            self.harness.charm._state
        )
        self.assertEqual(dict(local_job_storage.get_labels()), {})
        local_job_storage.add("my-job")
        self.assertIn("my-job", local_job_storage.get_labels())

    def test_run_once_per_unit(self) -> None:
        """Test run_once_per_unit decorator."""
        self.harness.charm._state.run_once = {}
        call_counter = self.harness.charm.unit_job_counter
        self.harness.charm.unit_specific_job()
        expected_count = call_counter + 1
        self.assertEqual(expected_count, self.harness.charm.unit_job_counter)
        self.harness.charm.unit_specific_job()
        # The call count should be unchanged as the job should not have
        # run
        self.assertEqual(expected_count, self.harness.charm.unit_job_counter)
