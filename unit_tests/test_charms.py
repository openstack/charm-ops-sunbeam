#!/usr/bin/env python3

# Copyright 2020 Canonical Ltd.
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


import os
import tempfile
import sys

sys.path.append('lib')  # noqa
sys.path.append('src')  # noqa

import advanced_sunbeam_openstack.charm as sunbeam_charm

CHARM_CONFIG = {
    'region': 'RegionOne',
    'debug': 'true'}

CHARM_METADATA = '''
name: my-service
version: 3
bases:
  - name: ubuntu
    channel: 20.04/stable
tags:
  - openstack
  - identity
  - misc

subordinate: false

containers:
  my-service:
    resource: mysvc-image
    mounts:
      - storage: db
        location: /var/lib/mysvc

storage:
  logs:
    type: filesystem
  db:
    type: filesystem

resources:
  mysvc-image:
    type: oci-image
'''

API_CHARM_METADATA = '''
name: my-service
version: 3
bases:
  - name: ubuntu
    channel: 20.04/stable
tags:
  - openstack
  - identity
  - misc

subordinate: false

requires:
  shared-db:
    interface: mysql_datastore
    limit: 1
  ingress:
    interface: ingress
  amqp:
    interface: rabbitmq
  identity-service:
    interface: keystone

peers:
  peers:
    interface: mysvc-peer

containers:
  my-service:
    resource: mysvc-image
    mounts:
      - storage: db
        location: /var/lib/mysvc

storage:
  logs:
    type: filesystem
  db:
    type: filesystem

resources:
  mysvc-image:
    type: oci-image
'''


class MyCharm(sunbeam_charm.OSBaseOperatorCharm):

    openstack_release = 'diablo'
    service_name = 'my-service'

    def __init__(self, framework):
        self.seen_events = []
        self.render_calls = []
        self._template_dir = self._setup_templates()
        super().__init__(framework)

    def _log_event(self, event):
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(self, event):
        super()._on_service_pebble_ready(event)
        self._log_event(event)

    def _on_config_changed(self, event):
        self._log_event(event)

    def configure_charm(self, event):
        super().configure_charm(event)
        self._log_event(event)

    @property
    def public_ingress_port(self):
        return 789

    def _setup_templates(self):
        tmpdir = tempfile.mkdtemp()
        _template_dir = f'{tmpdir}/templates'
        os.mkdir(_template_dir)
        with open(f'{_template_dir}/my-service.conf.j2', 'w') as f:
            f.write("")
        return _template_dir

    @property
    def template_dir(self):
        return self._template_dir


TEMPLATE_CONTENTS = """
{{ wsgi_config.wsgi_admin_script }}
{{ shared_db.database_password }}
{{ options.debug }}
{{ amqp.transport_url }}
{{ amqp.hostname }}
{{ identity_service.service_password }}
{{ peers.foo }}
"""


class MyAPICharm(sunbeam_charm.OSBaseOperatorAPICharm):
    openstack_release = 'diablo'
    service_name = 'my-service'
    wsgi_admin_script = '/bin/wsgi_admin'
    wsgi_public_script = '/bin/wsgi_public'

    def __init__(self, framework):
        self.seen_events = []
        self.render_calls = []
        self._template_dir = self._setup_templates()
        super().__init__(framework)

    def _setup_templates(self):
        tmpdir = tempfile.mkdtemp()
        _template_dir = f'{tmpdir}/templates'
        os.mkdir(_template_dir)
        with open(f'{_template_dir}/my-service.conf.j2', 'w') as f:
            f.write(TEMPLATE_CONTENTS)
        with open(f'{_template_dir}/wsgi-my-service.conf.j2', 'w') as f:
            f.write(TEMPLATE_CONTENTS)
        return _template_dir

    def _log_event(self, event):
        self.seen_events.append(type(event).__name__)

    def _on_service_pebble_ready(self, event):
        super()._on_service_pebble_ready(event)
        self._log_event(event)

    def _on_config_changed(self, event):
        self._log_event(event)

    @property
    def default_public_ingress_port(self):
        return 789

    @property
    def template_dir(self):
        return self._template_dir
