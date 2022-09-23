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

"""Base classes for defining a charm using the Operator framework."""

import json
import logging
import cryptography.hazmat.primitives.serialization as serialization
from typing import Callable, List, Tuple, Optional
from urllib.parse import urlparse

import ops.charm
import ops.framework

import ops_sunbeam.interfaces as sunbeam_interfaces

logger = logging.getLogger(__name__)

ERASURE_CODED = "erasure-coded"
REPLICATED = "replacated"


class RelationHandler(ops.charm.Object):
    """Base handler class for relations.

    A relation handler is used to manage a charms interaction with a relation
    interface. This includes:

    1) Registering handlers to process events from the interface. The last
       step of these handlers is to make a callback to a specified method
       within the charm `callback_f`
    2) Expose a `ready` property so the charm can check a relations readyness
    3) A `context` method which returns a dict which pulls together data
       recieved and sent on an interface.
    """

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        super().__init__(
            charm,
            # Ensure we can have multiple instances of a relation handler,
            # but only one per relation.
            key=type(self).__name__ + '_' + relation_name
        )
        self.charm = charm
        self.relation_name = relation_name
        self.callback_f = callback_f
        self.interface = self.setup_event_handler()
        self.mandatory = mandatory

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for the relation.

        This method must be overridden in concrete class
        implementations.
        """
        raise NotImplementedError

    def get_interface(self) -> Tuple[ops.charm.Object, str]:
        """Return the interface that this handler encapsulates.

        This is a combination of the interface object and the
        name of the relation its wired into.
        """
        return self.interface, self.relation_name

    def interface_properties(self) -> dict:
        """Extract properties of the interface."""
        property_names = [
            p
            for p in dir(self.interface)
            if isinstance(getattr(type(self.interface), p, None), property)
        ]
        properties = {
            p: getattr(self.interface, p)
            for p in property_names
            if not p.startswith("_") and p not in ["model"]
        }
        return properties

    @property
    def ready(self) -> bool:
        """Determine with the relation is ready for use."""
        raise NotImplementedError

    def context(self) -> dict:
        """Pull together context for rendering templates."""
        return self.interface_properties()


class IngressHandler(RelationHandler):
    """Base class to handle Ingress relations."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        service_name: str,
        default_ingress_port: int,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.default_ingress_port = default_ingress_port
        self.service_name = service_name
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Ingress relation."""
        logger.debug("Setting up ingress event handler")
        from charms.traefik_k8s.v1.ingress import IngressPerAppRequirer
        interface = IngressPerAppRequirer(
            self.charm,
            self.relation_name,
            port=self.default_ingress_port,
        )
        self.framework.observe(
            interface.on.ready, self._on_ingress_ready
        )
        self.framework.observe(
            interface.on.revoked, self._on_ingress_revoked
        )
        return interface

    def _on_ingress_ready(self, event) -> None:  # noqa: ANN001
        """
        Handle ingress relation changed events.

        `event` is an instance of
        `charms.traefik_k8s.v1.ingress.IngressPerAppReadyEvent`.
        """
        url = self.url
        logger.debug(f'Received url: {url}')
        if not url:
            return

        self.callback_f(event)

    def _on_ingress_revoked(self, event) -> None:  # noqa: ANN001
        """
        Handle ingress relation revoked event.

        `event` is an instance of
        `charms.traefik_k8s.v1.ingress.IngressPerAppRevokedEvent`
        """
        # Callback call to update keystone endpoints
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether the handler is ready for use."""
        # Nothing to wait for
        if self.interface.url:
            return True

        return False

    @property
    def url(self) -> str:
        """Return the URL used by the remote ingress service."""
        if not self.ready:
            return None

        return self.interface.url

    def context(self) -> dict:
        """Context containing ingress data."""
        parse_result = urlparse(self.url)
        return {
            'ingress_path': parse_result.path,
        }


class IngressInternalHandler(IngressHandler):
    """Handler for Ingress relations on internal interface."""


class IngressPublicHandler(IngressHandler):
    """Handler for Ingress relations on public interface."""


class DBHandler(RelationHandler):
    """Handler for DB relations."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        database: str,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        # a database name as requested by the charm.
        self.database_name = database
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for a MySQL relation."""
        logger.debug("Setting up DB event handler")
        # Import here to avoid import errors if ops_sunbeam is being used
        # with a charm that doesn't want a DBHandler
        # and doesn't install this database_requires library.
        from charms.data_platform_libs.v0.database_requires import (
            DatabaseRequires
        )
        # Alias is required to events for this db
        # from trigger handlers for other dbs.
        # It also must be a valid python identifier.
        alias = self.relation_name.replace("-", "_")
        db = DatabaseRequires(
            self.charm, self.relation_name, self.database_name,
            relations_aliases=[alias]
        )
        self.framework.observe(
            # db.on[f"{alias}_database_created"], # this doesn't work because:
            # RuntimeError: Framework.observe requires a BoundEvent as
            # second parameter, got <ops.framework.PrefixedEvents object ...
            getattr(db.on, f"{alias}_database_created"),
            self._on_database_updated
        )
        self.framework.observe(
            getattr(db.on, f"{alias}_endpoints_changed"),
            self._on_database_updated
        )
        # this will be set to self.interface in parent class
        return db

    def _on_database_updated(self, event: ops.framework.EventBase) -> None:
        """Handle database change events."""
        if not (event.username or event.password or event.endpoints):
            return

        data = event.relation.data[event.relation.app]
        # XXX: Let's not log the credentials with the data
        logger.info(f"Received data: {data}")
        self.callback_f(event)

    def get_relation_data(self) -> dict:
        """Load the data from the relation for consumption in the handler."""
        if len(self.interface.relations) > 0:
            return self.interface.relations[0].data[
                self.interface.relations[0].app
            ]
        return {}

    @property
    def ready(self) -> bool:
        """Whether the handler is ready for use."""
        data = self.get_relation_data()
        return bool(
            data.get("endpoints") and
            data.get("username") and
            data.get("password")
        )

    def context(self) -> dict:
        """Context containing database connection data."""
        if not self.ready:
            return {}

        data = self.get_relation_data()
        database_name = self.database_name
        database_host = data["endpoints"]
        database_user = data["username"]
        database_password = data["password"]
        database_type = "mysql+pymysql"
        has_tls = data.get("tls")
        tls_ca = data.get("tls-ca")

        connection = (
            f"{database_type}://{database_user}:{database_password}"
            f"@{database_host}/{database_name}"
        )
        if has_tls:
            connection = connection + f"?ssl_ca={tls_ca}"

        # This context ends up namespaced under the relation name
        # (normalised to fit a python identifier - s/-/_/),
        # and added to the context for jinja templates.
        # eg. if this DBHandler is added with relation name api-database,
        # the database connection string can be obtained in templates with
        # `api_database.connection`.
        return {
            "database": database_name,
            "database_host": database_host,
            "database_password": database_password,
            "database_user": database_user,
            "database_type": database_type,
            "connection": connection,
        }


class AMQPHandler(RelationHandler):
    """Handler for managing a amqp relation."""

    DEFAULT_PORT = "5672"

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        username: str,
        vhost: int,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.username = username
        self.vhost = vhost
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an AMQP relation."""
        logger.debug("Setting up AMQP event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        import charms.sunbeam_rabbitmq_operator.v0.amqp as sunbeam_amqp
        amqp = sunbeam_amqp.AMQPRequires(
            self.charm, self.relation_name, self.username, self.vhost
        )
        self.framework.observe(amqp.on.ready, self._on_amqp_ready)
        return amqp

    def _on_amqp_ready(self, event: ops.framework.EventBase) -> None:
        """Handle AMQP change events."""
        # Ready is only emitted when the interface considers
        # that the relation is complete (indicated by a password)
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.password)
        except AttributeError:
            return False

    def context(self) -> dict:
        """Context containing AMQP connection data."""
        try:
            hosts = self.interface.hostnames
        except AttributeError:
            return {}
        if not hosts:
            return {}
        ctxt = super().context()
        ctxt["hostnames"] = list(set(ctxt["hostnames"]))
        ctxt["hosts"] = ",".join(ctxt["hostnames"])
        ctxt["port"] = ctxt.get("ssl_port") or self.DEFAULT_PORT
        transport_url_hosts = ",".join(
            [
                "{}:{}@{}:{}".format(
                    self.username,
                    ctxt["password"],
                    host_,  # TODO deal with IPv6
                    ctxt["port"],
                )
                for host_ in ctxt["hostnames"]
            ]
        )
        transport_url = "rabbit://{}/{}".format(
            transport_url_hosts, self.vhost
        )
        ctxt["transport_url"] = transport_url
        return ctxt


class IdentityServiceRequiresHandler(RelationHandler):
    """Handler for managing a identity-service relation."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        service_endpoints: dict,
        region: str,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.service_endpoints = service_endpoints
        self.region = region
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Identity service relation."""
        logger.debug("Setting up Identity Service event handler")
        import charms.sunbeam_keystone_operator.v0.identity_service as sun_id
        id_svc = sun_id.IdentityServiceRequires(
            self.charm, self.relation_name, self.service_endpoints, self.region
        )
        self.framework.observe(
            id_svc.on.ready, self._on_identity_service_ready
        )
        return id_svc

    def _on_identity_service_ready(
        self, event: ops.framework.EventBase
    ) -> None:
        """Handle AMQP change events."""
        # Ready is only emitted when the interface considers
        # that the relation is complete (indicated by a password)
        self.callback_f(event)

    def update_service_endpoints(self, service_endpoints: dict) -> None:
        """Update service endpoints on the relation."""
        self.service_endpoints = service_endpoints
        self.interface.register_services(service_endpoints, self.region)

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.service_password)
        except AttributeError:
            return False


class BasePeerHandler(RelationHandler):
    """Base handler for managing a peers relation."""

    LEADER_READY_KEY = "leader_ready"

    def setup_event_handler(self) -> None:
        """Configure event handlers for peer relation."""
        logger.debug("Setting up peer event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        peer_int = sunbeam_interfaces.OperatorPeers(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            peer_int.on.peers_relation_joined, self._on_peers_relation_joined
        )
        self.framework.observe(
            peer_int.on.peers_data_changed, self._on_peers_data_changed
        )
        return peer_int

    def _on_peers_relation_joined(
            self, event: ops.framework.EventBase) -> None:
        """Process peer joined event."""
        self.callback_f(event)

    def _on_peers_data_changed(self, event: ops.framework.EventBase) -> None:
        """Process peer data changed event."""
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether the handler is complete."""
        return bool(self.interface.peers_rel)

    def context(self) -> dict:
        """Return all app data set on the peer relation."""
        try:
            _db = {
                k.replace('-', '_'): v
                for k, v in self.interface.get_all_app_data().items()}
            return _db
        except AttributeError:
            return {}

    def set_app_data(self, settings: dict) -> None:
        """Store data in peer app db."""
        self.interface.set_app_data(settings)

    def get_app_data(self, key: str) -> Optional[str]:
        """Retrieve data from the peer relation."""
        return self.interface.get_app_data(key)

    def leader_get(self, key: str) -> str:
        """Retrieve data from the peer relation."""
        return self.peers.get_app_data(key)

    def leader_set(self, settings: dict, **kwargs) -> None:
        """Store data in peer app db."""
        settings = settings or {}
        settings.update(kwargs)
        self.set_app_data(settings)

    def set_leader_ready(self) -> None:
        """Tell peers the leader is ready."""
        self.set_app_data({self.LEADER_READY_KEY: json.dumps(True)})

    def is_leader_ready(self) -> bool:
        """Whether the leader has announced it is ready."""
        ready = self.get_app_data(self.LEADER_READY_KEY)
        if ready is None:
            return False
        else:
            return json.loads(ready)


class CephClientHandler(RelationHandler):
    """Handler for ceph-client interface."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        allow_ec_overwrites: bool = True,
        app_name: str = None,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.allow_ec_overwrites = allow_ec_overwrites
        self.app_name = app_name
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an ceph-client interface."""
        logger.debug("Setting up ceph-client event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        import interface_ceph_client.ceph_client as ceph_client
        ceph = ceph_client.CephClientRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            ceph.on.pools_available, self._on_pools_available
        )
        self.framework.observe(
            ceph.on.broker_available, self.request_pools
        )
        return ceph

    def _on_pools_available(self, event: ops.framework.EventBase) -> None:
        """Handle pools available event."""
        # Ready is only emitted when the interface considers
        # that the relation is complete
        self.callback_f(event)

    def request_pools(self, event: ops.framework.EventBase) -> None:
        """
        Request Ceph pool creation when interface broker is ready.

        The default handler will automatically request erasure-coded
        or replicated pools depending on the configuration of the
        charm from which the handler is being used.

        To provide charm specific behaviour, subclass the default
        handler and use the required broker methods on the underlying
        interface object.
        """
        config = self.model.config.get
        data_pool_name = (
            config("rbd-pool-name") or
            config("rbd-pool") or
            self.charm.app.name
        )
        metadata_pool_name = (
            config("ec-rbd-metadata-pool") or f"{self.charm.app.name}-metadata"
        )
        weight = config("ceph-pool-weight")
        replicas = config("ceph-osd-replication-count")
        # TODO: add bluestore compression options
        if config("pool-type") == ERASURE_CODED:
            # General EC plugin config
            plugin = config("ec-profile-plugin")
            technique = config("ec-profile-technique")
            device_class = config("ec-profile-device-class")
            bdm_k = config("ec-profile-k")
            bdm_m = config("ec-profile-m")
            # LRC plugin config
            bdm_l = config("ec-profile-locality")
            crush_locality = config("ec-profile-crush-locality")
            # SHEC plugin config
            bdm_c = config("ec-profile-durability-estimator")
            # CLAY plugin config
            bdm_d = config("ec-profile-helper-chunks")
            scalar_mds = config("ec-profile-scalar-mds")
            # Profile name
            profile_name = (
                config("ec-profile-name") or f"{self.charm.app.name}-profile"
            )
            # Metadata sizing is approximately 1% of overall data weight
            # but is in effect driven by the number of rbd's rather than
            # their size - so it can be very lightweight.
            metadata_weight = weight * 0.01
            # Resize data pool weight to accomodate metadata weight
            weight = weight - metadata_weight
            # Create erasure profile
            self.interface.create_erasure_profile(
                name=profile_name,
                k=bdm_k,
                m=bdm_m,
                lrc_locality=bdm_l,
                lrc_crush_locality=crush_locality,
                shec_durability_estimator=bdm_c,
                clay_helper_chunks=bdm_d,
                clay_scalar_mds=scalar_mds,
                device_class=device_class,
                erasure_type=plugin,
                erasure_technique=technique,
            )

            # Create EC data pool
            self.interface.create_erasure_pool(
                name=data_pool_name,
                erasure_profile=profile_name,
                weight=weight,
                allow_ec_overwrites=self.allow_ec_overwrites,
                app_name=self.app_name,
            )
            # Create EC metadata pool
            self.interface.create_replicated_pool(
                name=metadata_pool_name,
                replicas=replicas,
                weight=metadata_weight,
                app_name=self.app_name,
            )
        else:
            self.interface.create_replicated_pool(
                name=data_pool_name, replicas=replicas, weight=weight,
                app_name=self.app_name,
            )

    @property
    def ready(self) -> bool:
        """Whether handler ready for use."""
        return self.interface.pools_available

    @property
    def key(self) -> str:
        """Retrieve the cephx key provided for the application."""
        return self.interface.get_relation_data().get('key')

    def context(self) -> dict:
        """Context containing Ceph connection data."""
        ctxt = super().context()
        data = self.interface.get_relation_data()
        ctxt['mon_hosts'] = ",".join(
            sorted(data.get("mon_hosts"))
        )
        ctxt['auth'] = data.get('auth')
        ctxt['key'] = data.get("key")
        ctxt['rbd_features'] = None
        return ctxt


class CertificatesHandler(RelationHandler):
    """Handler for certificates interface."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        sans: List[str] = None,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        import interface_tls_certificates.ca_client as ca_client
        self.ca_client = ca_client
        self.sans = sans
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> None:
        """Configure event handlers for peer relation."""
        logger.debug("Setting up certificates event handler")
        certs = self.ca_client.CAClient(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            certs.on.ca_available,
            self._request_certs)
        self.framework.observe(
            certs.on.tls_server_config_ready,
            self._certs_ready)
        return certs

    def _request_certs(self, event: ops.framework.EventBase) -> None:
        """Request Certificates."""
        logger.debug(f"Requesting cert for {self.sans}")
        self.interface.request_server_certificate(
            self.model.unit.name.replace('/', '-'),
            self.sans)
        self.callback_f(event)

    def _certs_ready(self, event: ops.framework.EventBase) -> None:
        """Request Certificates."""
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether handler ready for use."""
        return self.interface.is_server_cert_ready

    def context(self) -> dict:
        """Certificates context."""
        key = self.interface.server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption())
        cert = self.interface.server_certificate.public_bytes(
            encoding=serialization.Encoding.PEM)
        try:
            root_ca_chain = self.interface.root_ca_chain.public_bytes(
                encoding=serialization.Encoding.PEM
            )
        except self.ca_client.CAClientError:
            # A root ca chain is not always available. If configured to just
            # use vault with self-signed certificates, you will not get a ca
            # chain. Instead, you will get a CAClientError being raised. For
            # now, use a bytes() object for the root_ca_chain as it shouldn't
            # cause problems and if a ca_cert_chain comes later, then it will
            # get updated.
            root_ca_chain = bytes()
        ca_cert = (
            self.interface.ca_certificate.public_bytes(
                encoding=serialization.Encoding.PEM) +
            root_ca_chain)
        ctxt = {
            'key': key.decode(),
            'cert': cert.decode(),
            'ca_cert': ca_cert.decode()}
        return ctxt


class CloudCredentialsRequiresHandler(RelationHandler):
    """Handles the cloud credentials relation on the requires side."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Create a new cloud-credentials handler.

        Create a new CloudCredentialsRequiresHandler that handles initial
        events from the relation and invokes the provided callbacks based on
        the event raised.

        :param charm: the Charm class the handler is for
        :type charm: ops.charm.CharmBase
        :param relation_name: the relation the handler is bound to
        :type relation_name: str
        :param callback_f: the function to call when the nodes are connected
        :type callback_f: Callable
        """
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for cloud-credentials relation."""
        import charms.sunbeam_keystone_operator.v0.cloud_credentials as \
            cloud_credentials
        logger.debug('Setting up the cloud-credentials event handler')
        credentials_service = cloud_credentials.CloudCredentialsRequires(
            self.charm, self.relation_name,
        )
        self.framework.observe(
            credentials_service.on.ready,
            self._credentials_ready
        )
        return credentials_service

    def _credentials_ready(self, event: ops.framework.EventBase) -> None:
        """React to credential ready event."""
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.password)
        except AttributeError:
            return False
