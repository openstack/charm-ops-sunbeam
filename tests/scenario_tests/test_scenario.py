#!/usr/bin/env python3

# Copyright 2023 Canonical Ltd.
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

"""Test charms for unit tests."""
from . import test_fixtures
from . import scenario_utils as utils
import re
import sys

sys.path.append("tests/lib")  # noqa
sys.path.append("src")  # noqa

import pytest
from scenario import (
    State,
    Context,
    Container,
    Mount,
)
from ops.model import (
    ActiveStatus,
    MaintenanceStatus,
)


class TestOSBaseOperatorCharmScenarios:
    @pytest.mark.parametrize("leader", (True, False))
    def test_no_relations(self, leader):
        """Check charm with no relations becomes active."""
        state = State(leader=leader, config={}, containers=[])
        ctxt = Context(
            charm_type=test_fixtures.MyCharm,
            meta=test_fixtures.MyCharm_Metadata,
        )
        out = ctxt.run("install", state)
        assert out.unit_status == MaintenanceStatus(
            "(bootstrap) Service not bootstrapped"
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status == ActiveStatus("")

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.missing_relation(test_fixtures.MyCharmMulti_Metadata),
    )
    def test_relation_missing(self, relations, leader):
        """Check charm with a missing relation is blocked."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmMulti,
            meta=test_fixtures.MyCharmMulti_Metadata,
        )
        state = State(
            leader=True,
            config={},
            containers=[],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status.name == "blocked"
        assert re.match(r".*integration missing", out.unit_status.message)

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.incomplete_relation(test_fixtures.MyCharmMulti_Metadata),
    )
    def test_relation_incomplete(self, relations, leader):
        """Check charm with an incomplete relation is waiting."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmMulti,
            meta=test_fixtures.MyCharmMulti_Metadata,
        )
        state = State(
            leader=True,
            config={},
            containers=[],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status.name == "waiting"
        assert re.match(
            r".*Not all relations are ready", out.unit_status.message
        )

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.complete_relation(test_fixtures.MyCharmMulti_Metadata),
    )
    def test_relations_complete(self, relations, leader):
        """Check charm with complete relations is active."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmMulti,
            meta=test_fixtures.MyCharmMulti_Metadata,
        )
        state = State(
            leader=True,
            config={},
            containers=[],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status == ActiveStatus("")


class TestOSBaseOperatorCharmK8SScenarios:
    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations", utils.missing_relation(test_fixtures.MyCharmK8S_Metadata)
    )
    def test_relation_missing(self, tmp_path, relations, leader):
        """Check k8s charm with a missing relation is blocked."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8S,
            meta=test_fixtures.MyCharmK8S_Metadata,
        )
        p1 = tmp_path / "c1"
        p2 = tmp_path / "c2"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="container1",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p1)},
                ),
                Container(
                    name="container2",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p2)},
                ),
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert re.match(r".*integration missing", out.unit_status.message)
        assert out.unit_status.name == "blocked"

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.incomplete_relation(test_fixtures.MyCharmK8S_Metadata),
    )
    def test_relation_incomplete(self, tmp_path, relations, leader):
        """Check k8s charm with an incomplete relation is waiting."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8S,
            meta=test_fixtures.MyCharmK8S_Metadata,
        )
        p1 = tmp_path / "c1"
        p2 = tmp_path / "c2"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="container1",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p1)},
                ),
                Container(
                    name="container2",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p2)},
                ),
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status.name == "waiting"
        assert re.match(
            r".*Not all relations are ready", out.unit_status.message
        )

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations", utils.complete_relation(test_fixtures.MyCharmK8S_Metadata)
    )
    def test_relation_container_not_ready(self, tmp_path, relations, leader):
        """Check k8s charm with container is cannot connect to it waiting ."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8S,
            meta=test_fixtures.MyCharmK8S_Metadata,
        )
        p1 = tmp_path / "c1"
        p2 = tmp_path / "c2"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="container1",
                    can_connect=False,
                    mounts={"local": Mount("/etc", p1)},
                ),
                Container(
                    name="container2",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p2)},
                ),
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status.name == "waiting"
        assert re.match(
            r".*Payload container not ready", out.unit_status.message
        )

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations", utils.complete_relation(test_fixtures.MyCharmK8S_Metadata)
    )
    def test_relation_all_complete(self, tmp_path, relations, leader):
        """Check k8s charm with complete rels & ready containers is active."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8S,
            meta=test_fixtures.MyCharmK8S_Metadata,
        )
        p1 = tmp_path / "c1"
        p2 = tmp_path / "c2"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="container1",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p1)},
                ),
                Container(
                    name="container2",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p2)},
                ),
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status == ActiveStatus("")


class TestOSBaseOperatorCharmK8SAPIScenarios:
    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.missing_relation(test_fixtures.MyCharmK8SAPI_Metadata),
    )
    def test_relation_missing(self, tmp_path, relations, leader):
        """Check k8s API charm with a missing relation is blocked."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8SAPI,
            meta=test_fixtures.MyCharmK8SAPI_Metadata,
        )
        p1 = tmp_path / "c1"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="my-service",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p1)},
                )
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert re.match(r".*integration missing", out.unit_status.message)
        assert out.unit_status.name == "blocked"

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.incomplete_relation(test_fixtures.MyCharmK8SAPI_Metadata),
    )
    def test_relation_incomplete(self, tmp_path, relations, leader):
        """Check k8s API charm with an incomplete relation is waiting."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8SAPI,
            meta=test_fixtures.MyCharmK8SAPI_Metadata,
        )
        p1 = tmp_path / "c1"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="my-service",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p1)},
                )
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status.name == "waiting"
        assert re.match(
            r".*Not all relations are ready", out.unit_status.message
        )

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.complete_relation(test_fixtures.MyCharmK8SAPI_Metadata),
    )
    def test_relation_container_not_ready(self, tmp_path, relations, leader):
        """Check k8s API charm with stopped container is waiting."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8SAPI,
            meta=test_fixtures.MyCharmK8SAPI_Metadata,
        )
        p1 = tmp_path / "c1"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="my-service",
                    can_connect=False,
                    mounts={"local": Mount("/etc", p1)},
                )
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status.name == "waiting"
        assert re.match(
            r".*Payload container not ready", out.unit_status.message
        )

    @pytest.mark.parametrize("leader", (True, False))
    @pytest.mark.parametrize(
        "relations",
        utils.complete_relation(test_fixtures.MyCharmK8SAPI_Metadata),
    )
    def test_relation_all_complete(self, tmp_path, relations, leader):
        """Check k8s API charm all rels and containers are ready."""
        ctxt = Context(
            charm_type=test_fixtures.MyCharmK8SAPI,
            meta=test_fixtures.MyCharmK8SAPI_Metadata,
        )
        p1 = tmp_path / "c1"
        state = State(
            leader=True,
            config={},
            containers=[
                Container(
                    name="my-service",
                    can_connect=True,
                    mounts={"local": Mount("/etc", p1)},
                )
            ],
            relations=list(relations),
            secrets=[utils.get_keystone_secret_definition(relations)],
        )
        out = ctxt.run("config-changed", state)
        assert out.unit_status == ActiveStatus("")
