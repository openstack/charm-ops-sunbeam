=============================
How-To Write a pebble handler
=============================

A pebble handler sits between a charm and a container it manages. A pebble
handler presents the charm with a consistent method of interaction with
the container. For example the charm can query the handler to check config
has been rendered and services started. It can call the `execute` method
to run commands in the container or call `write_config` to render the
defined files into the container.

Common Pebble handler changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ASO provides a pebble handler base classes which provide the starting point
for writing a new handler. If the container runs a service then the
`ServicePebbleHandler` should be used. If the container does not provide a
service (perhaps it's just an environment for executing commands that affect
other containers) then `PebbleHandler` should be used.

.. code:: python

    import ops_sunbeam.container_handlers as sunbeam_chandlers

    class MyServicePebbleHandler(sunbeam_chandlers.ServicePebbleHandler):
        """Manage MyService Container."""

The handlers can create directories in the container once the pebble is
available.

.. code:: python

        @property
        def directories(self) -> List[sunbeam_chandlers.ContainerDir]:
            """Directories to create in container."""
            return [
                sunbeam_chandlers.ContainerDir(
                    '/var/log/my-service',
                    'root',
                    'root')]

In addition to directories the handler can list configuration files which need
to be rendered into the container. These will be rendered as templates using
all available contexts.

.. code:: python

    def default_container_configs(
        self
    ) -> List[sunbeam_core.ContainerConfigFile]:
        """Files to render into containers."""
        return [
            sunbeam_core.ContainerConfigFile(
                '/etc/mysvc/mvsvc.conf',
                'root',
                'root')]

If a service should be running in the container the handler specifies the
layer describing the service that will be passed to pebble.

.. code:: python

    def get_layer(self) -> dict:
        """Pebble configuration layer for MyService service."""
        return {
            "summary": "My service",
            "description": "Pebble config layer for MyService",
            "services": {
                'my_svc': {
                    "override": "replace",
                    "summary": "My Super Service",
                    "command": "/usr/bin/my-svc",
                    "startup": "disabled",
                },
            },
        }


Advanced Pebble handler changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default the pebble handler is the observer of pebble events. If this
behaviour needs to be altered then `setup_pebble_handler` method can be
changed.

.. code:: python

    def setup_pebble_handler(self) -> None:
        """Configure handler for pebble ready event."""
        pass

Or perhaps it is ok for the pebble handler to observe the event but a
different reaction is required. In this case the method associated
with the event can be overridden.

.. code:: python

     def _on_service_pebble_ready(
        self, event: ops.charm.PebbleReadyEvent
     ) -> None:
        """Handle pebble ready event."""
        container = event.workload
        container.add_layer(self.service_name, self.get_layer(), combine=True)
        self.execute(["run", "special", "command"])
        logger.debug(f"Plan: {container.get_plan()}")
        self.ready = True
        self.charm.configure_charm(event)

Configuring Charm to use custom pebble handler
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The charms `get_pebble_handlers` method dictates which pebble handlers are used.

.. code:: python

    class MyCharmCharm(NeutronOperatorCharm):

        def get_pebble_handlers(self) -> List[sunbeam_chandlers.PebbleHandler]:
            """Pebble handlers for the service."""
            return [
                MyServicePebbleHandler(
                    self,
                    'my-server-container',
                    self.service_name,
                    self.container_configs,
                    self.template_dir,
                    self.openstack_release,
                    self.configure_charm,
                )
            ]
