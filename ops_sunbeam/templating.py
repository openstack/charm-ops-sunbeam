# Copyright 2021, Canonical Ltd.
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

"""Module for rendering templates inside containers."""

import logging
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    import ops_sunbeam.core as sunbeam_core
    import ops.model

from charmhelpers.contrib.openstack.templating import get_loader
import jinja2

log = logging.getLogger(__name__)


def get_container(
    containers: List['ops.model.Container'], name: str
) -> 'ops.model.Container':
    """Search for container with given name inlist of containers."""
    container = None
    for c in containers:
        if c.name == name:
            container = c
    return container


def sidecar_config_render(
    container: 'ops.model.Container',
    config: 'sunbeam_core.ContainerConfigFile',
    template_dir: str,
    openstack_release: str,
    context: 'sunbeam_core.OPSCharmContexts',
) -> None:
    """Render templates inside containers."""
    loader = get_loader(template_dir, openstack_release)
    _tmpl_env = jinja2.Environment(loader=loader)
    try:
        template = _tmpl_env.get_template(
            os.path.basename(config.path) + ".j2"
        )
    except jinja2.exceptions.TemplateNotFound:
        template = _tmpl_env.get_template(
            os.path.basename(config.path)
        )
    contents = template.render(context)
    kwargs = {
        "user": config.user,
        "group": config.group,
        "permissions": config.permissions}
    parent_dir = str(Path(config.path).parent)
    if not container.isdir(parent_dir):
        container.make_dir(parent_dir, make_parents=True)
    container.push(config.path, contents, **kwargs)
    log.debug(
        f"Wrote template {config.path} in container {container.name}."
    )
