import ops_openstack.adapters

class ConfigAdapter():

    def __init__(self, charm, namespace):
        self.charm = charm
        self.namespace = namespace
        for k, v in self.context().items():
            k = k.replace('-', '_')
            setattr(self, k, v)


class CharmConfigAdapter(ConfigAdapter):

    def context(self):
        return self.charm.config


class WSGIWorkerConfigAdapter(ConfigAdapter):

    def context(self):
        return {
            'name': self.charm.service_name,
            'wsgi_admin_script': self.charm.wsgi_admin_script,
            'wsgi_public_script': self.charm.wsgi_public_script}


class DBAdapter(ops_openstack.adapters.OpenStackOperRelationAdapter):

    @property
    def database(self):
        return self.relation.databases()[0]

    @property
    def database_host(self):
        return self.relation.credentials().get('address')

    @property
    def database_password(self):
        return self.relation.credentials().get('password')

    @property
    def database_user(self):
        return self.relation.credentials().get('username')

    @property
    def database_type(self):
        return 'mysql+pymysql'


class AMQPAdapter(ops_openstack.adapters.OpenStackOperRelationAdapter):

    DEFAULT_PORT = "5672"

    @property
    def port(self):
        """Return the AMQP port

        :returns: AMQP port number
        :rtype: string
        """
        return self.relation.ssl_port or self.DEFAULT_PORT

    @property
    def hosts(self):
        """
        Comma separated list of hosts that should be used
        to access RabbitMQ.
        """
        hosts = self.relation.hostnames
        if len(hosts) > 1:
            return ','.join(hosts)
        else:
            return None

    @property
    def transport_url(self) -> str:
        """
        oslo.messaging formatted transport URL

        :returns: oslo.messaging formatted transport URL
        :rtype: string
        """
        hosts = self.relation.hostnames
        transport_url_hosts = ','.join([
            "{}:{}@{}:{}".format(self.username,
                                 self.password,
                                 host_,  # TODO deal with IPv6
                                 self.port)
            for host_ in hosts
        ])
        return "rabbit://{}/{}".format(transport_url_hosts, self.vhost)


class OPSRelationAdapters():

    def __init__(self, charm):
        self.charm = charm
        self.namespaces = []

    def _get_adapter(self, relation_name):
        # Matching relation first
        # Then interface name
        if self.relation_map.get(relation_name):
            return self.relation_map.get(relation_name)
        interface_name = self.charm.meta.relations[
            relation_name].interface_name
        if self.interface_map.get(interface_name):
            return self.interface_map.get(interface_name)

    def add_relation_adapter(self, interface, relation_name):
        adapter = self._get_adapter(relation_name)
        if adapter:
            adapter_ns = relation_name.replace("-", "_")
            self.namespaces.append(adapter_ns)
            setattr(self, adapter_ns, adapter(interface))
        else:
            logging.debug(f"No adapter found for {relation_name}")

    def add_config_adapters(self, config_adapters):
        for config_adapter in config_adapters:
            self.add_config_adapter(
                config_adapter,
                config_adapter.namespace)

    def add_config_adapter(self, config_adapter, namespace):
        self.namespaces.append(namespace)
        setattr(self, namespace, config_adapter)

    @property
    def interface_map(self):
        return {}

    @property
    def relation_map(self):
        return {}

    def __iter__(self):
        """
        Iterate over the relations presented to the charm.
        """
        for namespace in self.namespaces:
            yield namespace, getattr(self, namespace)


class APICharmAdapters(OPSRelationAdapters):
    """Collection of relation adapters."""

    @property
    def interface_map(self):
        _map = super().interface_map
        _map.update({
            'mysql_datastore': DBAdapter})
        return _map
