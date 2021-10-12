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

"""Base classes for defining a charm using the Operator framework.

"""

import logging
from collections.abc import Callable
from typing import Tuple

import ops.charm

import charms.nginx_ingress_integrator.v0.ingress as ingress
import charms.mysql.v1.mysql as mysql
import charms.sunbeam_rabbitmq_operator.v0.amqp as sunbeam_amqp

logger = logging.getLogger(__name__)


class RelationHandler(ops.charm.Object):
    """Base handler class for relations

    A relation handler is used to manage a charms interaction with a relation
    interface. This includes:

    1) Registering handlers to process events from the interface. The last
       step of these handlers is to make a callback to a specified method
       within the charm `callback_f`
    2) Expose a `ready` property so the charm can check a relations readyness
    3) A `context` method which returns a dict which pulls together data
       recieved and sent on an interface.
    """

    def __init__(self, charm: ops.charm.CharmBase,
                 relation_name: str, callback_f: Callable):
        super().__init__(charm, None)
        self.charm = charm
        self.relation_name = relation_name
        self.callback_f = callback_f
        self.interface = self.setup_event_handler()

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for the relation.

        This method must be overridden in concrete class
        implementations.
        """
        raise NotImplementedError

    def get_interface(self) -> Tuple[ops.charm.Object, str]:
        """Returns the interface that this handler encapsulates.

        This is a combination of the interface object and the
        name of the relation its wired into.
        """
        return self.interface, self.relation_name

    def interface_properties(self):
        property_names = [
            p for p in dir(self.interface) if isinstance(
                getattr(type(self.interface), p, None), property)]
        properties = {
            p: getattr(self.interface, p)
            for p in property_names
            if not p.startswith('_') and p not in ['model']}
        return properties

    @property
    def ready(self) -> bool:
        """Determine with the relation is ready for use."""
        raise NotImplementedError

    def context(self) -> dict:
        """Pull together context for rendering templates."""
        return self.interface_properties()


class IngressHandler(RelationHandler):
    """Handler for Ingress relations"""

    def __init__(self, charm: ops.charm.CharmBase,
                 relation_name: str,
                 service_name: str,
                 default_public_ingress_port: int,
                 callback_f: Callable):
        self.default_public_ingress_port = default_public_ingress_port
        self.service_name = service_name
        super().__init__(charm, relation_name, callback_f)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Ingress relation."""
        logger.debug('Setting up ingress event handler')
        interface = ingress.IngressRequires(
            self.charm,
            self.ingress_config)
        return interface

    @property
    def ingress_config(self) -> dict:
        """Ingress controller configuration dictionary."""
        # Most charms probably won't (or shouldn't) expose service-port
        # but use it if its there.
        port = self.model.config.get(
            'service-port',
            self.default_public_ingress_port)
        svc_hostname = self.model.config.get(
            'os-public-hostname',
            self.service_name)
        return {
            'service-hostname': svc_hostname,
            'service-name': self.charm.app.name,
            'service-port': port}

    @property
    def ready(self) -> bool:
        # Nothing to wait for
        return True

    def context(self):
        return {}


class DBHandler(RelationHandler):
    """Handler for DB relations"""

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for a MySQL relation."""
        logger.debug('Setting up DB event handler')
        db = mysql.MySQLConsumer(
            self.charm,
            self.relation_name,
            {"mysql": ">=8"})
        _rname = self.relation_name.replace('-', '_')
        db_relation_event = getattr(
            self.charm.on,
            f'{_rname}_relation_changed')
        self.framework.observe(db_relation_event,
                               self._on_database_changed)
        return db

    def _on_database_changed(self, event) -> None:
        """Handles database change events."""
        databases = self.interface.databases()
        logger.info(f'Received databases: {databases}')

        if not databases:
            logger.info('Requesting a new database...')
            # The mysql-k8s operator creates a database using the relation
            # information in the form of:
            #   db_{relation_id}_{partial_uuid}_{name_suffix}
            # where name_suffix defaults to "". Specify it to the name of the
            # current app to make it somewhat understandable as to what this
            # database actually is for.
            # NOTE(wolsen): database name cannot contain a '-'
            name_suffix = self.charm.app.name.replace('-', '_')
            self.interface.new_database(name_suffix=name_suffix)
            return
        credentials = self.interface.credentials()
        # XXX Lets not log the credentials
        logger.info(f'Received credentials: {credentials}')
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Handler ready for use."""
        try:
            # Nothing to wait for
            return bool(self.interface.databases())
        except AttributeError:
            return False

    def context(self):
        try:
            databases = self.interface.databases()
        except AttributeError:
            return {}
        if not databases:
            return {}
        ctxt = {
            'database': self.interface.databases()[0],
            'database_host': self.interface.credentials().get('address'),
            'database_password': self.interface.credentials().get('password'),
            'database_user': self.interface.credentials().get('username'),
            'database_type': 'mysql+pymysql'}
        return ctxt


class AMQPHandler(RelationHandler):

    DEFAULT_PORT = "5672"

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f,
        username: str,
        vhost: int,
    ):
        self.username = username
        self.vhost = vhost
        super().__init__(charm, relation_name, callback_f)

    def setup_event_handler(self):
        """Configure event handlers for an AMQP relation."""
        logger.debug("Setting up AMQP event handler")
        amqp = sunbeam_amqp.AMQPRequires(
            self.charm, self.relation_name, self.username, self.vhost
        )
        self.framework.observe(amqp.on.ready, self._on_amqp_ready)
        return amqp

    def _on_amqp_ready(self, event) -> None:
        """Handles AMQP change events."""
        # Ready is only emitted when the interface considers
        # that the relation is complete (indicated by a password)
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Handler ready for use."""
        try:
            return bool(self.interface.password)
        except AttributeError:
            return False

    def context(self):
        try:
            hosts = self.interface.hostnames
        except AttributeError:
            return {}
        if not hosts:
            return {}
        ctxt = super().context()
        ctxt['hostnames'] = list(set(ctxt['hostnames']))
        ctxt['hosts'] = ','.join(ctxt['hostnames'])
        ctxt['port'] = ctxt.get('ssl_port') or self.DEFAULT_PORT
        transport_url_hosts = ','.join([
            "{}:{}@{}:{}".format(self.username,
                                 ctxt['password'],
                                 host_,  # TODO deal with IPv6
                                 ctxt['port'])
            for host_ in ctxt['hostnames']
        ])
        transport_url = "rabbit://{}/{}".format(
            transport_url_hosts,
            self.vhost)
        ctxt['transport_url'] = transport_url
        return ctxt
