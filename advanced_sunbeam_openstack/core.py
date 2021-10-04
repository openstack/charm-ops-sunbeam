#!/usr/bin/env python3
# Copyright 2021 Billy Olsen
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import collections
import logging

import advanced_sunbeam_openstack.adapters as sunbeam_adapters
import advanced_sunbeam_openstack.templating as sunbeam_templating
import advanced_sunbeam_openstack.cprocess as sunbeam_cprocess

import charms.nginx_ingress_integrator.v0.ingress as ingress
import charms.mysql.v1.mysql as mysql

import ops.charm
import ops.framework
import ops.model

from collections.abc import Callable
from typing import List, Tuple
from ops_openstack.adapters import OpenStackOperRelationAdapter

logger = logging.getLogger(__name__)


ContainerConfigFile = collections.namedtuple(
    'ContainerConfigFile',
    ['container_names', 'path', 'user', 'group'])


class PebbleHandler(ops.charm.Object):
    """Base handler for Pebble based containers."""

    _state = ops.framework.StoredState()

    def __init__(self, charm: ops.charm.CharmBase,
                 container_name: str, service_name: str,
                 container_configs: List[ContainerConfigFile],
                 template_dir: str, openstack_release: str,
                 adapters: List[OpenStackOperRelationAdapter],
                 callback_f: Callable):
        super().__init__(charm, None)
        self._state.set_default(pebble_ready=False)
        self._state.set_default(config_pushed=False)
        self._state.set_default(service_ready=False)
        self.charm = charm
        self.container_name = container_name
        self.service_name = service_name
        self.container_configs = container_configs
        self.container_configs.extend(self.default_container_configs())
        self.template_dir = template_dir
        self.openstack_release = openstack_release
        self.adapters = adapters
        self.callback_f = callback_f
        self.setup_pebble_handler()

    def setup_pebble_handler(self) -> None:
        """Configure handler for pebble ready event."""
        prefix = self.container_name.replace('-', '_')
        pebble_ready_event = getattr(
            self.charm.on,
            f'{prefix}_pebble_ready')
        self.framework.observe(pebble_ready_event,
                               self._on_service_pebble_ready)

    def _on_service_pebble_ready(self,
                                 event: ops.charm.PebbleReadyEvent) -> None:
        """Handle pebble ready event."""
        container = event.workload
        container.add_layer(
            self.service_name,
            self.get_layer(),
            combine=True)
        logger.debug(f'Plan: {container.get_plan()}')
        self.ready = True
        self.charm.configure_charm(event)
        self._state.pebble_ready = True

    def write_config(self) -> None:
        """Write configuration files into the container.

        On the pre-condition that all relation adapters are ready
        for use, write all configuration files into the container
        so that the underlying service may be started.
        """
        for adapter in self.adapters:
            if not adapter[1].ready:
                logger.info("Adapter incomplete")
                return
        container = self.charm.unit.get_container(
            self.container_name)
        if container:
            sunbeam_templating.sidecar_config_render(
                [container],
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters)
            self._state.config_pushed = True
        else:
            logger.debug(
                'Container not ready')

    def get_layer(self) -> dict:
        """Pebble configuration layer for the container"""
        return {}

    def init_service(self) -> None:
        """Initialise service ready for use.

        Write configuration files to the container and record
        that service is ready for us.
        """
        self.write_config()
        self._state.service_ready = True

    def default_container_configs(self) -> List[ContainerConfigFile]:
        """Generate default container configurations.

        These should be used by all inheriting classes and are
        automatically added to the list or container configurations
        provided during object instantiation.
        """
        return []

    @property
    def pebble_ready(self) -> bool:
        """Determine if pebble is running and ready for use."""
        return self._state.pebble_ready

    @property
    def config_pushed(self) -> bool:
        """Determine if configuration has been pushed to the container."""
        return self._state.config_pushed

    @property
    def service_ready(self) -> bool:
        """Determine whether the service the container provides is running."""
        return self._state.service_ready


class WSGIPebbleHandler(PebbleHandler):
    """WSGI oriented handler for a Pebble managed container."""

    def __init__(self, charm: ops.charm.CharmBase,
                 container_name: str, service_name: str,
                 container_configs: List[ContainerConfigFile],
                 template_dir: str, openstack_release: str,
                 adapters: List[OpenStackOperRelationAdapter],
                 callback_f: Callable,
                 wsgi_service_name: str):
        super().__init__(charm, container_name, service_name,
                         container_configs, template_dir, openstack_release,
                         adapters, callback_f)
        self.wsgi_service_name = wsgi_service_name

    def start_wsgi(self) -> None:
        """Start WSGI service"""
        container = self.charm.unit.get_container(self.container_name)
        if not container:
            logger.debug(f'{self.container_name} container is not ready. '
                         'Cannot start wgi service.')
            return
        service = container.get_service(self.wsgi_service_name)
        if service.is_running():
            container.stop(self.wsgi_service_name)

        container.start(self.wsgi_service_name)

    def get_layer(self) -> dict:
        """Apache WSGI service pebble layer

        :returns: pebble layer configuration for wsgi service
        """
        return {
            'summary': f'{self.service_name} layer',
            'description': 'pebble config layer for apache wsgi',
            'services': {
                f'{self.wsgi_service_name}': {
                    'override': 'replace',
                    'summary': f'{self.service_name} wsgi',
                    'command': '/usr/sbin/apache2ctl -DFOREGROUND',
                    'startup': 'disabled',
                },
            },
        }

    def init_service(self) -> None:
        """Enable and start WSGI service"""
        container = self.charm.unit.get_container(self.container_name)
        self.write_config()
        try:
            sunbeam_cprocess.check_output(
                container,
                f'a2ensite {self.wsgi_service_name} && sleep 1')
        except sunbeam_cprocess.ContainerProcessError:
            logger.exception(
                f'Failed to enable {self.wsgi_service_name} site in apache')
            # ignore for now - pebble is raising an exited too quickly, but it
            # appears to work properly.
        self.start_wsgi()
        self._state.service_ready = True

    @property
    def wsgi_conf(self) -> str:
        return f'/etc/apache2/sites-available/wsgi-{self.service_name}.conf'

    def default_container_configs(self) -> List[ContainerConfigFile]:
        return [
            ContainerConfigFile(
                [self.container_name],
                self.wsgi_conf,
                'root',
                'root')]


class RelationHandler(ops.charm.Object):
    """Base handler class for relations"""

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

    @property
    def ready(self) -> bool:
        """Determine with the relation is ready for use."""
        raise NotImplementedError


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


class OSBaseOperatorCharm(ops.charm.CharmBase):
    """Base charms for OpenStack operators."""

    _state = ops.framework.StoredState()

    def __init__(self, framework, adapters=None):
        if adapters:
            self.adapters = adapters
        else:
            self.adapters = sunbeam_adapters.OPSRelationAdapters(self)
        super().__init__(framework)
        self.adapters.add_config_adapters(self.config_adapters)
        # Setup the observers for relationship events and pass the interfaces
        # to the adapter classes.
        self.relation_handlers = self.get_relation_handlers()
        for handler in self.relation_handlers:
            interface, relation_name = handler.get_interface()
            self.adapters.add_relation_adapter(
                interface,
                relation_name)
        self.pebble_handlers = self.get_pebble_handlers()
        self.framework.observe(self.on.config_changed,
                               self._on_config_changed)

    def get_relation_handlers(self) -> List[RelationHandler]:
        """Relation handlers for the operator."""
        return []

    def get_pebble_handlers(self) -> List[PebbleHandler]:
        """Pebble handlers for the operator."""
        return [
            PebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters,
                self.configure_charm)]

    def configure_charm(self, event) -> None:
        """Configure containers when all dependencies are met.

        Iterates over all Pebble handlers and writes configuration
        files if the handler is ready for use.
        """
        for h in self.pebble_handlers:
            if h.ready:
                h.write_config()

    @property
    def container_configs(self) -> List[ContainerConfigFile]:
        """Container configuration files for the operator."""
        return []

    @property
    def config_adapters(self) -> List[sunbeam_adapters.CharmConfigAdapter]:
        """Configuration adapters for the operator."""
        return [
            sunbeam_adapters.CharmConfigAdapter(self, 'options')]

    @property
    def handler_prefix(self) -> str:
        """Prefix for handlers??"""
        return self.service_name.replace('-', '_')

    @property
    def container_names(self):
        """Containers that form part of this service."""
        return [self.service_name]

    @property
    def template_dir(self) -> str:
        """Directory containing Jinja2 templates."""
        return 'src/templates'

    def _on_config_changed(self, event):
        self.configure_charm(None)

    def containers_ready(self) -> bool:
        """Determine whether all containers are ready for configuration."""
        for ph in self.pebble_handlers:
            if not ph.service_ready:
                logger.info(f"Container incomplete: {ph.container_name}")
                return False
        return True

    def relation_handlers_ready(self) -> bool:
        """Determine whether all relations are ready for use."""
        for handler in self.relation_handlers:
            if not handler.ready:
                logger.info(f"Relation {handler.relation_name} incomplete")
                return False
        return True


class OSBaseOperatorAPICharm(OSBaseOperatorCharm):
    """Base class for OpenStack API operators"""

    def __init__(self, framework, adapters=None):
        if not adapters:
            adapters = sunbeam_adapters.APICharmAdapters(self)
        super().__init__(framework, adapters)
        self._state.set_default(db_ready=False)
        self._state.set_default(bootstrapped=False)

    def get_pebble_handlers(self) -> List[PebbleHandler]:
        """Pebble handlers for the service"""
        return [
            WSGIPebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters,
                self.configure_charm,
                f'wsgi-{self.service_name}')]

    def get_relation_handlers(self) -> List[RelationHandler]:
        """Relation handlers for the service."""
        self.db = DBHandler(
            self,
            f'{self.service_name}-db',
            self.configure_charm)
        self.ingress = IngressHandler(
            self,
            'ingress',
            self.service_name,
            self.default_public_ingress_port,
            self.configure_charm)
        return [self.db, self.ingress]

    @property
    def container_configs(self) -> List[ContainerConfigFile]:
        """Container configuration files for the service."""
        _cconfigs = super().container_configs
        _cconfigs.extend([
            ContainerConfigFile(
                [self.wsgi_container_name],
                self.service_conf,
                self.service_user,
                self.service_group)])
        return _cconfigs

    @property
    def service_user(self) -> str:
        """Service user file and directory ownership."""
        return self.service_name

    @property
    def service_group(self) -> str:
        """Service group file and directory ownership."""
        return self.service_name

    @property
    def service_conf(self) -> str:
        """Service default configuration file."""
        return f'/etc/{self.service_name}/{self.service_name}.conf'

    @property
    def config_adapters(self) -> List[sunbeam_adapters.ConfigAdapter]:
        """Generate list of configuration adapters for the charm."""
        _cadapters = super().config_adapters
        _cadapters.extend([
            sunbeam_adapters.WSGIWorkerConfigAdapter(self, 'wsgi_config')])
        return _cadapters

    @property
    def wsgi_container_name(self) -> str:
        """Name of the WSGI application container."""
        return self.service_name

    @property
    def default_public_ingress_port(self) -> int:
        """Port to use for ingress access to service."""
        raise NotImplementedError

    def configure_charm(self, event) -> None:
        """Catchall handler to cconfigure charm services."""
        if not self.relation_handlers_ready():
            logging.debug("Aborting charm relations not ready")
            return

        for ph in self.pebble_handlers:
            if ph.pebble_ready:
                ph.init_service()

        for ph in self.pebble_handlers:
            if not ph.service_ready:
                logging.debug("Aborting container service not ready")
                return

        if not self.bootstrapped():
            self._do_bootstrap()

        self.unit.status = ops.model.ActiveStatus()
        self._state.bootstrapped = True

    def _do_bootstrap(self) -> None:
        """Bootstrap the service ready for operation.

        This method should be overridden as part of a concrete
        charm implementation
        """
        pass

    def bootstrapped(self) -> bool:
        """Determine whether the service has been boostrapped."""
        return self._state.bootstrapped
