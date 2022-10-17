"""RabbitMQProvides and Requires module.

This library contains the Requires and Provides classes for handling
the rabbitmq interface.

Import `RabbitMQRequires` in your charm, with the charm object and the
relation name:
    - self
    - "amqp"

Also provide two additional parameters to the charm object:
    - username
    - vhost

Two events are also available to respond to:
    - connected
    - ready
    - goneaway

A basic example showing the usage of this relation follows:

```
from charms.rabbitmq_k8s.v0.rabbitmq import RabbitMQRequires

class RabbitMQClientCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        # RabbitMQ Requires
        self.amqp = RabbitMQRequires(
            self, "amqp",
            username="myusername",
            vhost="vhostname"
        )
        self.framework.observe(
            self.amqp.on.connected, self._on_amqp_connected)
        self.framework.observe(
            self.amqp.on.ready, self._on_amqp_ready)
        self.framework.observe(
            self.amqp.on.goneaway, self._on_amqp_goneaway)

    def _on_amqp_connected(self, event):
        '''React to the RabbitMQ connected event.

        This event happens when n RabbitMQ relation is added to the
        model before credentials etc have been provided.
        '''
        # Do something before the relation is complete
        pass

    def _on_amqp_ready(self, event):
        '''React to the RabbitMQ ready event.

        The RabbitMQ interface will use the provided username and vhost for the
        request to the rabbitmq server.
        '''
        # RabbitMQ Relation is ready. Do something with the completed relation.
        pass

    def _on_amqp_goneaway(self, event):
        '''React to the RabbitMQ goneaway event.

        This event happens when an RabbitMQ relation is removed.
        '''
        # RabbitMQ Relation has goneaway. shutdown services or suchlike
        pass
```
"""

# The unique Charmhub library identifier, never change it
LIBID = "45622352791142fd9cf87232e3bd6f2a"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

import logging

from ops.framework import (
    StoredState,
    EventBase,
    ObjectEvents,
    EventSource,
    Object,
)

from ops.model import Relation

from typing import List

logger = logging.getLogger(__name__)


class RabbitMQConnectedEvent(EventBase):
    """RabbitMQ connected Event."""

    pass


class RabbitMQReadyEvent(EventBase):
    """RabbitMQ ready for use Event."""

    pass


class RabbitMQGoneAwayEvent(EventBase):
    """RabbitMQ relation has gone-away Event"""

    pass


class RabbitMQServerEvents(ObjectEvents):
    """Events class for `on`"""

    connected = EventSource(RabbitMQConnectedEvent)
    ready = EventSource(RabbitMQReadyEvent)
    goneaway = EventSource(RabbitMQGoneAwayEvent)


class RabbitMQRequires(Object):
    """
    RabbitMQRequires class
    """

    on = RabbitMQServerEvents()

    def __init__(self, charm, relation_name: str, username: str, vhost: str):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.username = username
        self.vhost = vhost
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_amqp_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_amqp_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_departed,
            self._on_amqp_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_amqp_relation_broken,
        )

    def _on_amqp_relation_joined(self, event):
        """RabbitMQ relation joined."""
        logging.debug("RabbitMQRabbitMQRequires on_joined")
        self.on.connected.emit()
        self.request_access(self.username, self.vhost)

    def _on_amqp_relation_changed(self, event):
        """RabbitMQ relation changed."""
        logging.debug("RabbitMQRabbitMQRequires on_changed/departed")
        if self.password:
            self.on.ready.emit()

    def _on_amqp_relation_broken(self, event):
        """RabbitMQ relation broken."""
        logging.debug("RabbitMQRabbitMQRequires on_broken")
        self.on.goneaway.emit()

    @property
    def _amqp_rel(self) -> Relation:
        """The RabbitMQ relation."""
        return self.framework.model.get_relation(self.relation_name)

    @property
    def password(self) -> str:
        """Return the RabbitMQ password from the server side of the relation."""
        return self._amqp_rel.data[self._amqp_rel.app].get("password")

    @property
    def hostname(self) -> str:
        """Return the hostname from the RabbitMQ relation"""
        return self._amqp_rel.data[self._amqp_rel.app].get("hostname")

    @property
    def ssl_port(self) -> str:
        """Return the SSL port from the RabbitMQ relation"""
        return self._amqp_rel.data[self._amqp_rel.app].get("ssl_port")

    @property
    def ssl_ca(self) -> str:
        """Return the SSL port from the RabbitMQ relation"""
        return self._amqp_rel.data[self._amqp_rel.app].get("ssl_ca")

    @property
    def hostnames(self) -> List[str]:
        """Return a list of remote RMQ hosts from the RabbitMQ relation"""
        _hosts = []
        for unit in self._amqp_rel.units:
            _hosts.append(self._amqp_rel.data[unit].get("ingress-address"))
        return _hosts

    def request_access(self, username: str, vhost: str) -> None:
        """Request access to the RabbitMQ server."""
        if self.model.unit.is_leader():
            logging.debug("Requesting RabbitMQ user and vhost")
            self._amqp_rel.data[self.charm.app]["username"] = username
            self._amqp_rel.data[self.charm.app]["vhost"] = vhost


class HasRabbitMQClientsEvent(EventBase):
    """Has RabbitMQClients Event."""

    pass


class ReadyRabbitMQClientsEvent(EventBase):
    """RabbitMQClients Ready Event."""

    pass


class RabbitMQClientEvents(ObjectEvents):
    """Events class for `on`"""

    has_amqp_clients = EventSource(HasRabbitMQClientsEvent)
    ready_amqp_clients = EventSource(ReadyRabbitMQClientsEvent)


class RabbitMQProvides(Object):
    """
    RabbitMQProvides class
    """

    on = RabbitMQClientEvents()

    def __init__(self, charm, relation_name, callback):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.callback = callback
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_amqp_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_amqp_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_amqp_relation_broken,
        )

    def _on_amqp_relation_joined(self, event):
        """Handle RabbitMQ joined."""
        logging.debug("RabbitMQRabbitMQProvides on_joined data={}"
                      .format(event.relation.data[event.relation.app]))
        self.on.has_amqp_clients.emit()

    def _on_amqp_relation_changed(self, event):
        """Handle RabbitMQ changed."""
        logging.debug("RabbitMQRabbitMQProvides on_changed data={}"
                      .format(event.relation.data[event.relation.app]))
        # Validate data on the relation
        if self.username(event) and self.vhost(event):
            self.on.ready_amqp_clients.emit()
            if self.charm.unit.is_leader():
                self.callback(event, self.username(event), self.vhost(event))
        else:
            logging.warning("Received RabbitMQ changed event without the "
                            "expected keys ('username', 'vhost') in the "
                            "application data bag.  Incompatible charm in "
                            "other end of relation?")

    def _on_amqp_relation_broken(self, event):
        """Handle RabbitMQ broken."""
        logging.debug("RabbitMQRabbitMQProvides on_departed")
        # TODO clear data on the relation

    def username(self, event):
        """Return the RabbitMQ username from the client side of the relation."""
        return event.relation.data[event.relation.app].get("username")

    def vhost(self, event):
        """Return the RabbitMQ vhost from the client side of the relation."""
        return event.relation.data[event.relation.app].get("vhost")
