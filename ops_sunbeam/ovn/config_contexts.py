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

"""Base classes for defining a config context using the Operator framework.

ConfigContext objects can be used when rendering templates. They idea is to
create reusable contexts which translate charm config, deployment state etc.
These are not specific to a relation.
"""

from .. import config_contexts as sunbeam_ccontexts


class OVNDBConfigContext(sunbeam_ccontexts.ConfigContext):
    """Context for OVN charms."""

    def context(self) -> dict:
        """Context for OVN certs and leadership."""
        return {
            "is_charm_leader": self.charm.unit.is_leader(),
            "ovn_key": "/etc/ovn/key_host",
            "ovn_cert": "/etc/ovn/cert_host",
            "ovn_ca_cert": "/etc/ovn/ovn-central.crt",
        }
