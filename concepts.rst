============================================
Advanced Sunbeam OpenStack OPS Charm Anatomy
============================================

Overview
--------

Advanced Sunbeam OpenStack is designed to help with writing charms that
use the `Charmed Operator Framework <https://juju.is/docs/sdk>`__ and are
deployed on Kubernetes. For the rest of this document when a charm is referred
to it is implied that it is a Charmed Operator framework charm on Kubernetes.

It general a charm interacts with relations, renders configuration files and manages
services. ASO gives a charm a consistent way of doing this by implementing
Container handlers and Relation handlers.

Relation Handlers
-----------------

The job of a relation handler is to sit between a charm and an interface. This
allows the charm to have a consistent way of interacting with an interface
even if the charms interfaces vary widely in the way they are implemented. For
example the handlers have a `ready` property which indicates whether all
required data has been received. They also have a `context` method which
takes any data from the interface and creates a dictionary with this data
and any additional derived settings.

The relation handlers also setup event observers allowing them execute any
common procedures when events are raised by the interface. When the charm
initialises the interface it provides a callback function. The handler method
set be the observer first processes the event and then calls the charms
callback method passing the event as an argument.

Required Side Relation Handlers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The handler should be initialised with any information that will need to be
sent to the provider charm. Ideally the relation and the handler should not
interact directly with the instance of the charm class other than to run the
callback method. A required side relation handler should pass the charms
`configure_charm` method as the callback method.

Provider Side Relation Handlers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These are likely to be lightweight as there main purpose is probably to
process incoming requests from other charms. The charm should provide a
callback method which can process these incoming request.

Container Handlers
------------------

The job of a container handler is to sit between a charm and a pebble
container. This is particularly useful when a set have charms use very
similar containers such as a container that provides a WSGI service via
Apache.

The Container handler manages writing configuration files to the container
and restarting services. The charm can also query the handler to find the
state of the container, configuration within the container and the status
of services within the container.a

When a Container handler is initialised the charm passes it a list of 
`ContainerConfigFile`. These objects instruct the handler which containers
a configuration file should be pushed to, the path to the configuration file
and the permission the file should have. The charm instructs the handler to
write the configuration files by calling the `init_service` method along with
a `OPSCharmContexts` object.

Contexts
--------

ASO supports two different types of context. `ConfigContext` and context from
relation handlers. These are all collected together in a single
`OPSCharmContexts`. The contexts from relation handlers are in a namespace
corresponding to the relation name. `ConfigContext` objects are in a namespace
explicitly named when the `ConfigContext` is created.

Relation Handler Context
~~~~~~~~~~~~~~~~~~~~~~~~

This context is provided by `RelationHandler.context()`. These context includes
all properties from the underlying interface and additional derived settings
added by the handler.

Configuration Context
~~~~~~~~~~~~~~~~~~~~~

These context do not relate directly to relations and are mainly a method of
sharing common transformations of charm configuration options to configuration
file entries. For example a WSGI configuration context might take a charm
configuration option, inspect the runtime environment and from the two derive
a third setting which is needed in a configuration file.

Interfaces
----------

An interface should live directly in a charm and be share via `charmcraft`
the only exception to this is the peer relation. ASO provides a base peer
interface and peer interface handler. This exposes methods which allow the lead
unit of an application to share data with its peers. It also allows a leader to
inform its peers when it is ready.

Templating
----------

Currently templates should be placed in `src/templates/`. If the charm is an
OpenStack charm the template file can be places in the subdirectory relating to
the relevant OpenStack release and the correct template will be selected.

Charms
------

ASO currently provides two base classes to choose from when writing a charm.
The first is `OSBaseOperatorCharm` and the second, which is derived from the
first, `OSBaseOperatorAPICharm`. 

The base classes setup a default set of relation handlers (based on what
relations are present in the charm metadata) and default container handlers.
These can easily be overridden by the charm if needed. The callback function
passed to the relation handlers is `configure_charm`. The `configure_charm`
method calculates whether the charm has all the prerequisites needed to render
configuration and start container services.

The `OSBaseOperatorAPICharm` class assumes that a WSGI service is being
configured and so adds the required container handler and configuration needed
for this.
