# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Common interfaces not charm specific."""

import logging
import typing

import ops.model

from ops.framework import EventBase
from ops.framework import EventSource
from ops.framework import Object
from ops.framework import ObjectEvents
from ops.framework import StoredState


class PeersRelationCreatedEvent(EventBase):
    """The PeersRelationCreatedEvent indicates that the peer relation now exists.

    It does not indicate that any peers are available or have joined, simply
    that the relation exists. This is useful to to indicate that the
    application databag is available for storing information shared across
    units.
    """

    pass


class PeersDataChangedEvent(EventBase):
    """The PeersDataChangedEvent indicates peer data hjas changed."""

    pass


class PeersEvents(ObjectEvents):
    """Peer Events."""

    peers_relation_created = EventSource(PeersRelationCreatedEvent)
    peers_data_changed = EventSource(PeersDataChangedEvent)


class OperatorPeers(Object):
    """Interface for the peers relation."""

    on = PeersEvents()
    state = StoredState()

    def __init__(self, charm: ops.charm.CharmBase, relation_name: str) -> None:
        """Run constructor."""
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.framework.observe(
            charm.on[relation_name].relation_created, self.on_created
        )
        self.framework.observe(
            charm.on[relation_name].relation_changed, self.on_changed
        )

    @property
    def peers_rel(self) -> ops.model.Relation:
        """Peer relation."""
        return self.framework.model.get_relation(self.relation_name)

    @property
    def _app_data_bag(self) -> typing.Dict[str, str]:
        """Return all app data on peer relation."""
        return self.peers_rel.data[self.peers_rel.app]

    def on_created(self, event: ops.framework.EventBase) -> None:
        """Handle relation created event."""
        logging.info("Peers on_created")
        self.on.peers_relation_created.emit()

    def on_changed(self, event: ops.framework.EventBase) -> None:
        """Handle relation changed event."""
        logging.info("Peers on_changed")
        self.on.peers_data_changed.emit()

    def set_app_data(self, settings: typing.Dict[str, str]) -> None:
        """Publish settings on the peer app data bag."""
        for k, v in settings.items():
            self._app_data_bag[k] = v

    def get_app_data(self, key: str) -> None:
        """Get the value corresponding to key from the app data bag."""
        return self._app_data_bag.get(key)

    def get_all_app_data(self) -> None:
        """Return all the app data from the relation."""
        return self._app_data_bag
