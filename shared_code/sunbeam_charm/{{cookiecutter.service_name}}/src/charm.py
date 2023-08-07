#!/usr/bin/env python3
"""{{ cookiecutter.service_name[0]|upper}}{{cookiecutter.service_name[1:] }} Operator Charm.

This charm provide {{ cookiecutter.service_name[0]|upper}}{{cookiecutter.service_name[1:] }} services as part of an OpenStack deployment
"""

import logging

from ops.framework import StoredState
from ops.main import main

import ops_sunbeam.charm as sunbeam_charm

logger = logging.getLogger(__name__)


class {{ cookiecutter.service_name[0]|upper}}{{cookiecutter.service_name[1:] }}OperatorCharm(sunbeam_charm.OSBaseOperatorAPICharm):
    """Charm the service."""

    _state = StoredState()
    service_name = "{{ cookiecutter.service_name }}-api"
    wsgi_admin_script = '/usr/bin/{{ cookiecutter.service_name }}-api-wsgi'
    wsgi_public_script = '/usr/bin/{{ cookiecutter.service_name }}-api-wsgi'

    db_sync_cmds = [
        {{ cookiecutter.db_sync_command.split() }}
    ]

    @property
    def service_conf(self) -> str:
        """Service default configuration file."""
        return "/etc/{{ cookiecutter.service_name }}/{{ cookiecutter.service_name }}.conf"

    @property
    def service_user(self) -> str:
        """Service user file and directory ownership."""
        return '{{ cookiecutter.service_name }}'

    @property
    def service_group(self) -> str:
        """Service group file and directory ownership."""
        return '{{ cookiecutter.service_name }}'

    @property
    def service_endpoints(self):
        """Return service endpoints for the service."""
        return [
            {
                'service_name': '{{ cookiecutter.service_name }}',
                'type': '{{ cookiecutter.service_name }}',
                'description': "OpenStack {{ cookiecutter.service_name[0]|upper}}{{cookiecutter.service_name[1:] }} API",
                'internal_url': f'{self.internal_url}',
                'public_url': f'{self.public_url}',
                'admin_url': f'{self.admin_url}'}]

    @property
    def default_public_ingress_port(self):
        """Ingress Port for API service."""
        return {{ cookiecutter.ingress_port }}


if __name__ == "__main__":
    main({{ cookiecutter.service_name[0]|upper}}{{cookiecutter.service_name[1:] }}OperatorCharm)
