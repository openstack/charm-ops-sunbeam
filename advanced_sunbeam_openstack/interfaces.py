#!/usr/bin/env python3

import logging
import typing

from ops.framework import EventBase
from ops.framework import EventSource
from ops.framework import Object
from ops.framework import ObjectEvents
from ops.framework import StoredState


class PeersRelationCreatedEvent(EventBase):
    """
    The PeersRelationCreatedEvent indicates that the peer relation now exists.
    It does not indicate that any peers are available or have joined, simply
    that the relation exists. This is useful to to indicate that the
    application databag is available for storing information shared across
    units.
    """
    pass


class PeersDataChangedEvent(EventBase):
    """
    The CharmPasswordChangedEvent indicates that the leader unit has changed
    the password that the charm administrator uses.
    """
    pass


class PeersEvents(ObjectEvents):
    peers_relation_created = EventSource(PeersRelationCreatedEvent)
    peers_data_changed = EventSource(PeersDataChangedEvent)


class OperatorPeers(Object):

    on = PeersEvents()
    state = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.framework.observe(
            charm.on[relation_name].relation_created,
            self.on_created
        )
        self.framework.observe(
            charm.on[relation_name].relation_changed,
            self.on_changed
        )

    @property
    def peers_rel(self):
        return self.framework.model.get_relation(self.relation_name)

    @property
    def _app_data_bag(self) -> typing.Dict[str, str]:
        """

        """
        return self.peers_rel.data[self.peers_rel.app]

    def on_created(self, event):
        logging.info('Peers on_created')
        self.on.peers_relation_created.emit()

    def on_changed(self, event):
        logging.info('Peers on_changed')
        self.on.peers_data_changed.emit()

    def set_app_data(self, key, value) -> None:
        """

        """
        self._app_data_bag[key] = value

    def get_app_data(self, key) -> None:
        """

        """
        return self._app_data_bag.get(key)

    def get_all_app_data(self) -> None:
        """

        """
        return self._app_data_bag
