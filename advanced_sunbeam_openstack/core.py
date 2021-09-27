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
import ops_openstack
import ops_openstack.adapters

from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from charms.mysql.v1.mysql import MySQLConsumer

from ops.charm import CharmBase
from ops.charm import PebbleReadyEvent
from ops import model

from ops.framework import StoredState

import advanced_sunbeam_openstack.adapters as sunbeam_adapters
from advanced_sunbeam_openstack.templating import sidecar_config_render
import advanced_sunbeam_openstack.cprocess as sunbeam_cprocess

logger = logging.getLogger(__name__)


ContainerConfigFile = collections.namedtuple(
    'ContainerConfigFile',
    ['container_names', 'path', 'user', 'group'])


class OSBaseOperatorCharm(CharmBase):
    _state = StoredState()

    def __init__(self, framework, adapters=None):
        if adapters:
            self.adapters = adapters
        else:
            self.adapters = sunbeam_adapters.OPSRelationAdapters(self)
        super().__init__(framework)
        self.adapters.add_config_adapters(self.config_adapters)
        self.framework.observe(self.on.config_changed,
                               self._on_config_changed)
        self.handlers = self.setup_event_handlers()

    @property
    def container_configs(self):
        return []

    @property
    def config_adapters(self):
        return [
            sunbeam_adapters.CharmConfigAdapter(self, 'options')]

    @property
    def handler_prefix(self):
        return self.service_name.replace('-', '_')

    @property
    def container_names(self):
        return [self.service_name]

    @property
    def template_dir(self):
        return 'src/templates'

    def renderer(self, containers, container_configs, template_dir,
                 openstack_release, adapters):
        sidecar_config_render(
            containers,
            self.container_configs,
            self.template_dir,
            self.openstack_release,
            self.adapters)

    def write_config(self):
        containers = [self.unit.get_container(c_name)
                      for c_name in self.container_names]
        if all(containers):
            self.renderer(
                containers,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters)
        else:
            logger.debug(
                'One or more containers are not ready')

    def setup_event_handlers(self):
        self.setup_pebble_handler()
        return []

    def setup_pebble_handler(self):
        pebble_ready_event = getattr(
            self.on,
            f'{self.handler_prefix}_pebble_ready')
        self.framework.observe(pebble_ready_event,
                               self._on_service_pebble_ready)

    def _on_service_pebble_ready(self, event: PebbleReadyEvent) -> None:
        self.configure_charm()

    def _on_config_changed(self, event):
        self.configure_charm()


class OSBaseOperatorAPICharm(OSBaseOperatorCharm):
    _state = StoredState()

    def __init__(self, framework, adapters=None):
        if not adapters:
            adapters = sunbeam_adapters.APICharmAdapters(self)
        super().__init__(framework, adapters)
        self._state.set_default(db_ready=False)
        self._state.set_default(bootstrapped=False)

    @property
    def container_configs(self):
        _cconfigs = super().container_configs
        _cconfigs.extend([
            ContainerConfigFile(
                [self.wsgi_container_name],
                self.service_conf,
                self.service_user,
                self.service_group),
            ContainerConfigFile(
                [self.wsgi_container_name],
                self.wsgi_conf,
                'root',
                'root')])
        return _cconfigs

    @property
    def service_user(self):
        return self.service_name

    @property
    def service_group(self):
        return self.service_name

    @property
    def service_conf(self):
        return f'/etc/{self.service_name}/{self.service_name}.conf'

    @property
    def config_adapters(self):
        _cadapters = super().config_adapters
        _cadapters.extend([
            sunbeam_adapters.WSGIWorkerConfigAdapter(self, 'wsgi_config')])
        return _cadapters

    @property
    def wsgi_admin_script(self):
        raise NotImplementedError

    @property
    def wsgi_public_script(self):
        raise NotImplementedError

    @property
    def wsgi_container_name(self):
        return self.service_name

    @property
    def wsgi_service_name(self):
        return f'{self.service_name}-wsgi'

    @property
    def wsgi_conf(self):
        return f'/etc/apache2/sites-available/{self.wsgi_service_name}.conf'

    @property
    def wsgi_service_name(self):
        return f'wsgi-{self.service_name}'

    @property
    def public_ingress_port(self):
        raise NotImplementedError

    @property
    def ingress_config(self):
        # Most charms probably won't (or shouldn't) expose service-port
        # but use it if its there.
        port = self.model.config.get('service-port', self.public_ingress_port)
        svc_hostname = self.model.config.get(
            'os-public-hostname',
            self.service_name)
        return {
            'service-hostname': svc_hostname,
            'service-name': self.app.name,
            'service-port': port}

    def setup_event_handlers(self):
        handlers = super().setup_event_handlers()
        handlers.extend([
            self.setup_db_event_handler(),
            self.setup_ingress_event_handler()])
        return handlers

    def setup_db_event_handler(self):
        logger.debug('Setting up DB event handler')
        relation_name = f'{self.service_name}-db'
        self.db = MySQLConsumer(
            self,
            f'{self.service_name}-db',
            {"mysql": ">=8"})
        self.adapters.add_relation_adapter(
            self.db,
            relation_name)
        db_relation_event = getattr(
            self.on,
            f'{self.handler_prefix}_db_relation_changed')
        self.framework.observe(db_relation_event,
                               self._on_database_changed)
        return self.db

    def _on_database_changed(self, event) -> None:
        """Handles database change events."""
        # self.unit.status = model.MaintenanceStatus('Updating database '
        #                                            'configuration')
        databases = self.db.databases()
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
            name_suffix = self.app.name.replace('-', '_')
            self.db.new_database(name_suffix=name_suffix)
            return
        credentials = self.db.credentials()
        logger.info(f'Received credentials: {credentials}')
        self._state.db_ready = True
        self.configure_charm()

    @property
    def db_ready(self):
        """Returns True if the remote database has been configured and is
        ready for access from the local service.

        :returns: True if the database is ready to be accessed, False otherwise
        :rtype: bool
        """
        return self._state.db_ready

    def setup_ingress_event_handler(self):
        logger.debug('Setting up ingress event handler')
        self.ingress_public = IngressRequires(
            self,
            self.ingress_config)
        return self.ingress_public

    def _on_service_pebble_ready(self, event: PebbleReadyEvent) -> None:
        container = event.workload
        container.add_layer(
            self.service_name,
            self.get_apache_layer(),
            combine=True)
        logger.debug(f'Plan: {container.get_plan()}')

    def get_apache_layer(self):
        """Apache WSGI service

        :returns: pebble layer configuration for wsgi services
        :rtype: dict
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

    def start_wsgi(self):
        container = self.unit.get_container(self.wsgi_container_name)
        if not container:
            logger.debug(f'{self.wsgi_container_name} container is not ready. '
                          'Cannot start wgi service.')
            return
        service = container.get_service(self.wsgi_service_name)
        if service.is_running():
            container.stop(self.wsgi_service_name)

        container.start(self.wsgi_service_name)


    def configure_charm(self):
        self._do_bootstrap()
        self.unit.status = model.ActiveStatus()
        self._state.bootstrapped = True


    def _do_bootstrap(self): 
        """Checks the services to see which services need to run depending
        on the current state."""

        if self.is_bootstrapped():
            logger.debug(f'{self.service_name} is already bootstrapped')
            return

        if not self.db_ready:
            logger.debug('Database not ready, not bootstrapping')
            self.unit.status = model.BlockedStatus('Waiting for database')
            return

        if not self.unit.is_leader():
            logger.debug('Deferring bootstrap to leader unit')
            self.unit.status = model.BlockedStatus('Waiting for leader to '
                                                   'bootstrap keystone')
            return

        container = self.unit.get_container(self.wsgi_container_name)
        if not container:
            logger.debug(f'{self.wsgi_container_name} container is not ready. Deferring bootstrap')
            return

        # Write the config files to the container
        self.write_config()

        try:
            sunbeam_cprocess.check_output(
                container,
                f'a2ensite {self.wsgi_service_name} && sleep 1')
        except sunbeam_cprocess.ContainerProcessError:
            logger.exception(f'Failed to enable {self.wsgi_service_name} site in apache')
            # ignore for now - pebble is raising an exited too quickly, but it
            # appears to work properly.
        self.start_wsgi()


    def is_bootstrapped(self):
        """Returns True if the instance is bootstrapped.

        :returns: True if the keystone service has been bootstrapped,
                  False otherwise
        :rtype: bool
        """
        return self._state.bootstrapped
