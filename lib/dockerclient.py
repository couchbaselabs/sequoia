import os
from docker import Client, tls

class DockerClient:
    def __init__(self, provider_spec):
        spec = provider_spec['docker']
        print spec
        protocol = spec['proto']
        tls_config = None 
        if protocol == 'https':
            cert_path = os.getenv('DOCKER_CERT_PATH')
            ca = spec.get('ca') or cert_path+'/ca.pem'
            cert = spec.get('cert') or cert_path+'/cert.pem'
            key = spec.get('key') or cert_path+'/key.pem'
            tls_config = tls.TLSConfig(client_cert=(cert, key),
                                       verify = key)
        base_url = "%s://%s:%s" % (spec['proto'], spec['host'], spec['port'])
        self.cli = Client(base_url=base_url, tls=tls_config)

    def teardown(self):
        print  self.cli.containers()
