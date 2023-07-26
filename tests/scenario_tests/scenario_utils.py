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

"""Utilities for writing sunbeam scenario tests."""

import functools
import itertools

from scenario import (
    Relation,
    Secret,
)

# Data used to create Relation objects. If an incomplete relation is being
# created only the 'endpoint', 'interface' and 'remote_app_name' key are
# used.
default_relations = {
    "amqp": {
        "endpoint": "amqp",
        "interface": "rabbitmq",
        "remote_app_name": "rabbitmq",
        "remote_app_data": {"password": "foo"},
        "remote_units_data": {0: {"ingress-address": "host1"}},
    },
    "identity-credentials": {
        "endpoint": "identity-credentials",
        "interface": "keystone-credentials",
        "remote_app_name": "keystone",
        "remote_app_data": {
            "api-version": "3",
            "auth-host": "keystone.local",
            "auth-port": "12345",
            "auth-protocol": "http",
            "internal-host": "keystone.internal",
            "internal-port": "5000",
            "internal-protocol": "http",
            "credentials": "foo",
            "project-name": "user-project",
            "project-id": "uproj-id",
            "user-domain-name": "udomain-name",
            "user-domain-id": "udomain-id",
            "project-domain-name": "pdomain_-ame",
            "project-domain-id": "pdomain-id",
            "region": "region12",
            "public-endpoint": "http://10.20.21.11:80/openstack-keystone",
            "internal-endpoint": "http://10.153.2.45:80/openstack-keystone",
        },
    },
}


def relation_combinations(
    metadata, one_missing=False, incomplete_relation=False
):
    """Based on a charms metadata generate tuples of relations.

    :param metadata: Dict of charm metadata
    :param one_missing: Bool if set then each unique relations tuple will be
                             missing one relation.
    :param one_missing: Bool if set then each unique relations tuple will
                             include one relation that has missing relation
                             data
    """
    _incomplete_relations = []
    _complete_relations = []
    _relation_pairs = []
    for rel_name in metadata.get("requires", {}):
        rel = default_relations[rel_name]
        complete_relation = Relation(
            endpoint=rel["endpoint"],
            interface=rel["interface"],
            remote_app_name=rel["remote_app_name"],
            local_unit_data=rel.get("local_unit_data", {}),
            remote_app_data=rel.get("remote_app_data", {}),
            remote_units_data=rel.get("remote_units_data", {}),
        )
        relation_missing_data = Relation(
            endpoint=rel["endpoint"],
            interface=rel["interface"],
            remote_app_name=rel["remote_app_name"],
        )
        _incomplete_relations.append(relation_missing_data)
        _complete_relations.append(complete_relation)
        _relation_pairs.append([relation_missing_data, complete_relation])

    if not (one_missing or incomplete_relation):
        return [tuple(_complete_relations)]
    if incomplete_relation:
        relations = list(itertools.product(*_relation_pairs))
        relations.remove(tuple(_complete_relations))
        return relations
    if one_missing:
        event_count = range(len(_incomplete_relations))
    else:
        event_count = range(len(_incomplete_relations) + 1)
    combinations = []
    for i in event_count:
        combinations.extend(
            list(itertools.combinations(_incomplete_relations, i))
        )
    return combinations


missing_relation = functools.partial(
    relation_combinations, one_missing=True, incomplete_relation=False
)
incomplete_relation = functools.partial(
    relation_combinations, one_missing=False, incomplete_relation=True
)
complete_relation = functools.partial(
    relation_combinations, one_missing=False, incomplete_relation=False
)


def get_keystone_secret_definition(relations):
    """Create the keystone identity secret."""
    ident_rel_id = None
    secret = None
    for relation in relations:
        if relation.remote_app_name == "keystone":
            ident_rel_id = relation.relation_id
    if ident_rel_id:
        secret = Secret(
            id="foo",
            contents={0: {"username": "svcuser1", "password": "svcpass1"}},
            owner="keystone",  # or 'app'
            remote_grants={ident_rel_id: {"my-service/0"}},
        )
    return secret
