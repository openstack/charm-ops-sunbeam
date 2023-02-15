=============================
How-To Write a config context
=============================

A config context is an additional context that is passed to the template
renderer in its own namespace. They are usually useful when some logic
needs to be applied to user supplied charm configuration. The context
has access to the charm object.

Below is an example which applies logic to the charm config as well as
collecting the application name to construct the context.

.. code:: python

    class CinderCephConfigurationContext(ConfigContext):
        """Cinder Ceph configuration context."""

        def context(self) -> None:
            """Cinder Ceph configuration context."""
            config = self.charm.model.config.get
            data_pool_name = config('rbd-pool-name') or self.charm.app.name
            if config('pool-type') == "erasure-coded":
                pool_name = (
                config('ec-rbd-metadata-pool') or
                f"{data_pool_name}-metadata"
                )
            else:
                pool_name = data_pool_name
            backend_name = config('volume-backend-name') or self.charm.app.name
            return {
                'cluster_name': self.charm.app.name,
                'rbd_pool': pool_name,
                'rbd_user': self.charm.app.name,
                'backend_name': backend_name,
                'backend_availability_zone': config('backend-availability-zone'),
            }

Configuring Charm to use custom config context
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The charm can append the new context onto those provided by the base class.

.. code:: python

    import ops_sunbeam.charm as sunbeam_charm

    class MyCharm(sunbeam_charm.OSBaseOperatorAPICharm):
       """Charm the service."""

        @property
        def config_contexts(self) -> List[sunbeam_ctxts.ConfigContext]:
            """Configuration contexts for the operator."""
            contexts = super().config_contexts
            contexts.append(
                sunbeam_ctxts.CinderCephConfigurationContext(self, "cinder_ceph"))
            return contexts
