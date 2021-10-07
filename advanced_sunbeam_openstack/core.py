import collections

ContainerConfigFile = collections.namedtuple(
    'ContainerConfigFile',
    ['container_names', 'path', 'user', 'group'])


class OPSCharmContexts():

    def __init__(self, charm):
        self.charm = charm
        self.namespaces = []

    def add_relation_handler(self, handler):
        interface, relation_name = handler.get_interface()
        _ns = relation_name.replace("-", "_")
        self.namespaces.append(_ns)
        ctxt = handler.context()
        obj_name = ''.join([w.capitalize() for w in relation_name.split('-')])
        obj = collections.namedtuple(obj_name, ctxt.keys())(*ctxt.values())
        setattr(self, _ns, obj)

    def add_config_contexts(self, config_adapters):
        for config_adapter in config_adapters:
            self.add_config_context(
                config_adapter,
                config_adapter.namespace)

    def add_config_context(self, config_adapter, namespace):
        self.namespaces.append(namespace)
        setattr(self, namespace, config_adapter)

    def __iter__(self):
        """
        Iterate over the relations presented to the charm.
        """
        for namespace in self.namespaces:
            yield namespace, getattr(self, namespace)
