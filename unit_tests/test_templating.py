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

"""Test ops_sunbeam.templating."""

import sys
from io import (
    BytesIO,
    TextIOWrapper,
)

import jinja2
import mock

sys.path.append("lib")  # noqa
sys.path.append("src")  # noqa

import ops_sunbeam.core as sunbeam_core
import ops_sunbeam.templating as sunbeam_templating
import ops_sunbeam.test_utils as test_utils


class TestTemplating(test_utils.CharmTestCase):
    """Tests for ops_sunbeam.templating.."""

    PATCHES = []

    def setUp(self) -> None:
        """Charm test class setup."""
        super().setUp(sunbeam_templating, self.PATCHES)

    @mock.patch("jinja2.FileSystemLoader")
    def test_render(self, fs_loader: "jinja2.FileSystemLoader") -> None:
        """Check rendering templates."""
        container_mock = mock.MagicMock()
        config = sunbeam_core.ContainerConfigFile(
            "/tmp/testfile.txt", "myuser", "mygrp"
        )
        fs_loader.return_value = jinja2.DictLoader(
            {"testfile.txt": "debug = {{ debug }}"}
        )
        sunbeam_templating.sidecar_config_render(
            container_mock, config, "/tmp/templates", "essex", {"debug": True}
        )
        container_mock.push.assert_called_once_with(
            "/tmp/testfile.txt",
            "debug = True",
            user="myuser",
            group="mygrp",
            permissions=None,
        )

    @mock.patch("jinja2.FileSystemLoader")
    def test_render_no_change(
        self, fs_loader: "jinja2.FileSystemLoader"
    ) -> None:
        """Check rendering template with no content change."""
        container_mock = mock.MagicMock()
        container_mock.pull.return_value = TextIOWrapper(
            BytesIO(b"debug = True")
        )
        config = sunbeam_core.ContainerConfigFile(
            "/tmp/testfile.txt", "myuser", "mygrp"
        )
        fs_loader.return_value = jinja2.DictLoader(
            {"testfile.txt": "debug = {{ debug }}"}
        )
        sunbeam_templating.sidecar_config_render(
            container_mock, config, "/tmp/templates", "essex", {"debug": True}
        )
        self.assertFalse(container_mock.push.called)
