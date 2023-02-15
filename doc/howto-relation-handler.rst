===============================
How-To Write a relation handler
===============================

A relation handler gives the charm a consistent method of interacting with
relation interfaces. It can also encapsulate common interface tasks, this
removes the need for duplicate code across multiple charms.

This how-to will walk through the steps to write a database relation handler
for the requires side.

In this database interface the database charm expects the client to provide the name
of the database(s) to be created. To model this the relation handler will require
the charm to specify the database name(s) when the class is instantiated.

.. code:: python

    class DBHandler(RelationHandler):
        """Handler for DB relations."""

        def __init__(
            self,
            charm: ops.charm.CharmBase,
            relation_name: str,
            callback_f: Callable,
            databases: List[str] = None,
        ) -> None:
            """Run constructor."""
            self.databases = databases
            super().__init__(charm, relation_name, callback_f)

The handler initialises the interface with the database names and also sets up
an observer for relation changed events.

.. code:: python

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for a MySQL relation."""
        logger.debug("Setting up DB event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        import charms.sunbeam_mysql_k8s.v0.mysql as mysql
        db = mysql.MySQLConsumer(
            self.charm, self.relation_name, databases=self.databases
        )
        _rname = self.relation_name.replace("-", "_")
        db_relation_event = getattr(
            self.charm.on, f"{_rname}_relation_changed"
        )
        self.framework.observe(db_relation_event, self._on_database_changed)
        return db

The method runs when the changed event is seen and checks whether all required
data has been provided. If it is then it calls back to the charm, if not then
no action is taken.

.. code:: python

    def _on_database_changed(self, event: ops.framework.EventBase) -> None:
        """Handle database change events."""
        databases = self.interface.databases()
        logger.info(f"Received databases: {databases}")
        if not self.ready:
            return
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether the handler is ready for use."""
        try:
            # Nothing to wait for
            return bool(self.interface.databases())
        except (AttributeError, KeyError):
            return False

The `ready` property is common across all handlers and allows the charm to
check the state of any relation in a consistent way.

The relation handlers also provide a context which can be used when rendering
templates. ASO places each relation context in its own namespace.

.. code:: python

    def context(self) -> dict:
        """Context containing database connection data."""
        try:
            databases = self.interface.databases()
        except (AttributeError, KeyError):
            return {}
        if not databases:
            return {}
        ctxt = {}
        conn_data = {
            "database_host": self.interface.credentials().get("address"),
            "database_password": self.interface.credentials().get("password"),
            "database_user": self.interface.credentials().get("username"),
            "database_type": "mysql+pymysql",
        }

        for db in self.interface.databases():
            ctxt[db] = {"database": db}
            ctxt[db].update(conn_data)
            connection = (
                "{database_type}://{database_user}:{database_password}"
                "@{database_host}/{database}")
            if conn_data.get("database_ssl_ca"):
                connection = connection + "?ssl_ca={database_ssl_ca}"
                if conn_data.get("database_ssl_cert"):
                    connection = connection + (
                        "&ssl_cert={database_ssl_cert}"
                        "&ssl_key={database_ssl_key}")
            ctxt[db]["connection"] = str(connection.format(
                **ctxt[db]))
        return ctxt

Configuring Charm to use custom relation handler
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The base class will add the default relation handlers for any interfaces
which do not yet have a handler. Therefore the custom handler is added to
the list and then passed to the super method. The base charm class will
see a handler already exists for database and not add the default one.

.. code:: python

    class MyCharm(sunbeam_charm.OSBaseOperatorAPICharm):
        """Charm the service."""

        def get_relation_handlers(self, handlers=None) -> List[
                sunbeam_rhandlers.RelationHandler]:
            """Relation handlers for the service."""
            handlers = handlers or []
            if self.can_add_handler("database", handlers):
                self.db = sunbeam_rhandlers.DBHandler(
                    self, "database", self.configure_charm, self.databases
                )
                handlers.append(self.db)
            handlers = super().get_relation_handlers(handlers)
            return handlers
