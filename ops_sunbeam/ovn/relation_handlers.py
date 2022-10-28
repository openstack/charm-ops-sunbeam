# Copyright 2022 Canonical Ltd.
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

"""Base classes for defining OVN relation handlers."""

import ipaddress
import itertools
import socket
import logging

from typing import Callable, Dict, Iterator, List

import ops.charm
import ops.framework

from .. import relation_handlers as sunbeam_rhandlers

logger = logging.getLogger(__name__)


class OVNRelationUtils():
    """Common utilities for processing OVN relations."""

    DB_NB_PORT = 6641
    DB_SB_PORT = 6642
    DB_SB_ADMIN_PORT = 16642
    DB_NB_CLUSTER_PORT = 6643
    DB_SB_CLUSTER_PORT = 6644

    def _format_addr(self, addr: str) -> str:
        """Validate and format IP address.

        :param addr: IPv6 or IPv4 address
        :type addr: str
        :returns: Address string, optionally encapsulated in brackets ([])
        :rtype: str
        :raises: ValueError
        """
        ipaddr = ipaddress.ip_address(addr)
        if isinstance(ipaddr, ipaddress.IPv6Address):
            fmt = '[{}]'
        else:
            fmt = '{}'
        return fmt.format(ipaddr)

    def _remote_addrs(self, key: str) -> Iterator[str]:
        """Retrieve addresses published by remote units.

        :param key: Relation data key to retrieve value from.
        :type key: str
        :returns: addresses published by remote units.
        :rtype: Iterator[str]
        """
        for addr in self.interface.get_all_unit_values(key):
            try:
                addr = self._format_addr(addr)
                yield addr
            except ValueError:
                continue

    def _remote_hostnames(self, key: str) -> Iterator[str]:
        """Retrieve hostnames published by remote units.

        :param key: Relation data key to retrieve value from.
        :type key: str
        :returns: hostnames published by remote units.
        :rtype: Iterator[str]
        """
        for hostname in self.interface.get_all_unit_values(key):
            yield hostname

    @property
    def cluster_remote_hostnames(self) -> Iterator[str]:
        """Retrieve remote hostnames bound to remote endpoint.

        :returns: hostnames bound to remote endpoints.
        :rtype: Iterator[str]
        """
        return self._remote_hostnames('bound-hostname')

    @property
    def cluster_remote_addrs(self) -> Iterator[str]:
        """Retrieve remote addresses bound to remote endpoint.

        :returns: addresses bound to remote endpoints.
        :rtype: Iterator[str]
        """
        return self._remote_addrs('bound-address')

    def db_connection_strs(
            self,
            hostnames: List[str],
            port: int,
            proto: str = 'ssl') -> Iterator[str]:
        """Provide connection strings.

        :param hostnames: List of hostnames to include in conn strs
        :type hostnames: List[str]
        :param port: Port number
        :type port: int
        :param proto: Protocol
        :type proto: str
        :returns: connection strings
        :rtype: Iterator[str]
        """
        for hostname in hostnames:
            yield ':'.join((proto, str(hostname), str(port)))

    @property
    def db_nb_port(self) -> int:
        """Provide port number for OVN Northbound OVSDB.

        :returns: port number for OVN Northbound OVSDB.
        :rtype: int
        """
        return self.DB_NB_PORT

    @property
    def db_sb_port(self) -> int:
        """Provide port number for OVN Southbound OVSDB.

        :returns: port number for OVN Southbound OVSDB.
        :rtype: int
        """
        return self.DB_SB_PORT

    @property
    def db_sb_admin_port(self) -> int:
        """Provide admin port number for OVN Southbound OVSDB.

        This is a special listener to allow ``ovn-northd`` to connect to an
        endpoint without RBAC enabled as there is currently no RBAC profile
        allowing ``ovn-northd`` to perform its work.

        :returns: admin port number for OVN Southbound OVSDB.
        :rtype: int
        """
        return self.DB_SB_ADMIN_PORT

    @property
    def db_nb_cluster_port(self) -> int:
        """Provide port number for OVN Northbound OVSDB.

        :returns port number for OVN Northbound OVSDB.
        :rtype: int
        """
        return self.DB_NB_CLUSTER_PORT

    @property
    def db_sb_cluster_port(self) -> int:
        """Provide port number for OVN Southbound OVSDB.

        :returns: port number for OVN Southbound OVSDB.
        :rtype: int
        """
        return self.DB_SB_CLUSTER_PORT

    @property
    def db_nb_connection_strs(self) -> Iterator[str]:
        """Provide OVN Northbound OVSDB connection strings.

        :returns: OVN Northbound OVSDB connection strings.
        :rtpye: Iterator[str]
        """
        return self.db_connection_strs(self.cluster_remote_addrs,
                                       self.db_nb_port)

    @property
    def db_sb_connection_strs(self) -> Iterator[str]:
        """Provide OVN Southbound OVSDB connection strings.

        :returns: OVN Southbound OVSDB connection strings.
        :rtpye: Iterator[str]
        """
        return self.db_connection_strs(self.cluster_remote_addrs,
                                       self.db_sb_port)

    @property
    def db_nb_connection_hostname_strs(self) -> Iterator[str]:
        """Provide OVN Northbound OVSDB connection strings.

        :returns: OVN Northbound OVSDB connection strings.
        :rtpye: Iterator[str]
        """
        return self.db_connection_strs(self.cluster_remote_hostnames,
                                       self.db_nb_port)

    @property
    def db_sb_connection_hostname_strs(self) -> Iterator[str]:
        """Provide OVN Southbound OVSDB connection strings.

        :returns: OVN Southbound OVSDB connection strings.
        :rtpye: Iterator[str]
        """
        return self.db_connection_strs(self.cluster_remote_hostnames,
                                       self.db_sb_port)

    @property
    def cluster_local_addr(self) -> ipaddress.IPv4Address:
        """Retrieve local address bound to endpoint.

        :returns: IPv4 or IPv6 address bound to endpoint
        :rtype: str
        """
        return self._endpoint_local_bound_addr()

    @property
    def cluster_local_hostname(self) -> str:
        """Retrieve local hostname for unit.

        :returns: Resolvable hostname for local unit.
        :rtype: str
        """
        return socket.getfqdn()

    def _endpoint_local_bound_addr(self) -> ipaddress.IPv4Address:
        """Retrieve local address bound to endpoint.

        :returns: IPv4 or IPv6 address bound to endpoint
        """
        addr = None
        for relation in self.charm.model.relations.get(self.relation_name, []):
            binding = self.charm.model.get_binding(relation)
            addr = binding.network.bind_address
            break
        return addr


class OVNDBClusterPeerHandler(sunbeam_rhandlers.BasePeerHandler,
                              OVNRelationUtils):
    """Handle OVN peer relation."""

    def publish_cluster_local_hostname(
            self,
            hostname: str = None) -> Dict:
        """Announce hostname on relation.

        This will be used by our peers and clients to build a connection
        string to the remote cluster.

        :param hostname: Override hostname to announce.
        :type hostname: Optional[str]
        """
        _hostname = hostname or self.cluster_local_hostname
        if _hostname:
            self.interface.set_unit_data({'bound-hostname': str(_hostname)})

    def expected_peers_available(self) -> bool:
        """Whether expected peers have joined and published data on peer rel.

        NOTE: This does not work for the normal inter-charm relations, please
              refer separate method for that in the shared interface library.

        :returns: True if expected peers have joined and published data,
                  False otherwise.
        :rtype: bool
        """
        joined_units = self.interface.all_joined_units()
        # Remove this unit from expected_peer_units count
        expected_remote_units = self.interface.expected_peer_units() - 1
        if len(joined_units) < expected_remote_units:
            logging.debug(
                f"Expected {expected_remote_units} but only {joined_units} "
                "have joined so far")
            return False
        hostnames = self.interface.get_all_unit_values('bound-hostname')
        if all(hostnames) < expected_remote_units:
            logging.debug(
                "Not all units have published a bound-hostname. Current "
                f"hostname list: {hostnames}")
            return False
        else:
            logging.debug(
                f"All expected peers are present. Hostnames: {hostnames}")
            return True

    @property
    def db_nb_connection_strs(self) -> Iterator[str]:
        """Provide Northbound DB connection strings.

        We override the parent property because for the peer relation
        ``cluster_remote_hostnames`` does not contain self.

        :returns: Northbound DB connection strings
        :rtype: Iterator[str]
        """
        return itertools.chain(
            self.db_connection_strs((self.cluster_local_hostname,),
                                    self.db_nb_port),
            self.db_connection_strs(self.cluster_remote_hostnames,
                                    self.db_nb_port))

    @property
    def db_nb_cluster_connection_strs(self) -> Iterator[str]:
        """Provide Northbound DB Cluster connection strings.

        We override the parent property because for the peer relation
        ``cluster_remote_hostnames`` does not contain self.

        :returns: Northbound DB connection strings
        :rtype: Iterator[str]
        """
        return itertools.chain(
            self.db_connection_strs((self.cluster_local_hostname,),
                                    self.db_nb_cluster_port),
            self.db_connection_strs(self.cluster_remote_hostnames,
                                    self.db_nb_cluster_port))

    @property
    def db_sb_cluster_connection_strs(self) -> Iterator[str]:
        """Provide Southbound DB Cluster connection strings.

        We override the parent property because for the peer relation
        ``cluster_remote_hostnames`` does not contain self.

        :returns: Southbound DB connection strings
        :rtype: Iterator[str]
        """
        return itertools.chain(
            self.db_connection_strs((self.cluster_local_hostname,),
                                    self.db_sb_cluster_port),
            self.db_connection_strs(self.cluster_remote_hostnames,
                                    self.db_sb_cluster_port))

    @property
    def db_sb_connection_strs(self) -> Iterator[str]:
        """Provide Southbound DB connection strings.

        We override the parent property because for the peer relation
        ``cluster_remote_hostnames`` does not contain self.  We use a different
        port for connecting to the SB DB as there is currently no RBAC profile
        that provide the privileges ``ovn-northd`` requires to operate.

        :returns: Southbound DB connection strings
        :rtype: Iterator[str]
        """
        return itertools.chain(
            self.db_connection_strs((self.cluster_local_hostname,),
                                    self.db_sb_admin_port),
            self.db_connection_strs(self.cluster_remote_hostnames,
                                    self.db_sb_admin_port))

    def _on_peers_relation_joined(
            self, event: ops.framework.EventBase) -> None:
        """Process peer joined event."""
        self.publish_cluster_local_hostname()

    def context(self) -> dict:
        """Context from relation data."""
        ctxt = super().context()
        ctxt.update({
            'cluster_local_hostname': self.cluster_local_hostname,
            'cluster_remote_hostnames': self.cluster_remote_hostnames,
            'db_nb_cluster_connection_strs':
                self.db_nb_cluster_connection_strs,
            'db_sb_cluster_connection_strs':
                self.db_sb_cluster_connection_strs,
            'db_sb_cluster_port': self.db_sb_cluster_port,
            'db_nb_cluster_port': self.db_nb_cluster_port,
            'db_nb_connection_strs': list(self.db_nb_connection_strs),
            'db_sb_connection_strs': list(self.db_sb_connection_strs)})
        return ctxt


class OVSDBCMSProvidesHandler(sunbeam_rhandlers.RelationHandler,
                              OVNRelationUtils):
    """Handle provides side of ovsdb-cms."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        super().__init__(charm, relation_name, callback_f, mandatory)
        self._update_address_data()

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Identity service relation."""
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        logger.debug("Setting up ovs-cms provides event handler")
        import charms.ovn_central_k8s.v0.ovsdb as ovsdb
        ovsdb_svc = ovsdb.OVSDBCMSProvides(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            ovsdb_svc.on.ready,
            self._on_ovsdb_service_ready)
        return ovsdb_svc

    def _on_ovsdb_service_ready(self, event: ops.framework.EventBase) -> None:
        """Handle OVSDB CMS change events."""
        self.callback_f(event)

    def _update_address_data(self) -> None:
        """Update hostname and IP address data on all relations."""
        self.interface.set_unit_data({
            'bound-hostname': str(self.cluster_local_hostname),
            'bound-address': str(self.cluster_local_addr),
        })

    @property
    def ready(self) -> bool:
        """Whether the interface is ready."""
        return True


class OVSDBCMSRequiresHandler(sunbeam_rhandlers.RelationHandler,
                              OVNRelationUtils):
    """Handle provides side of ovsdb-cms."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Identity service relation."""
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        logger.debug("Setting up ovs-cms requires event handler")
        import charms.ovn_central_k8s.v0.ovsdb as ovsdb
        ovsdb_svc = ovsdb.OVSDBCMSRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            ovsdb_svc.on.ready,
            self._on_ovsdb_service_ready)
        return ovsdb_svc

    def _on_ovsdb_service_ready(self, event: ops.framework.EventBase) -> None:
        """Handle OVSDB CMS change events."""
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether the interface is ready."""
        return self.interface.remote_ready()

    def context(self) -> dict:
        """Context from relation data."""
        ctxt = super().context()
        ctxt.update({
            'local_hostname': self.cluster_local_hostname,
            'hostnames': self.interface.bound_hostnames(),
            'local_address': self.cluster_local_addr,
            'addresses': self.interface.bound_addresses(),
            'db_sb_connection_strs': ','.join(self.db_sb_connection_strs),
            'db_nb_connection_strs': ','.join(self.db_nb_connection_strs),
            'db_sb_connection_hostname_strs':
                ','.join(self.db_sb_connection_hostname_strs),
            'db_nb_connection_hostname_strs':
                ','.join(self.db_nb_connection_hostname_strs)
        })

        return ctxt
