from dockerclient import DockerClient 

class TestDriver:
    def __init__(self, scope, test):
        self.scope = scope
        self.test = test 
        self.provider = DockerClient(scope)

    def run(self):
        self.provider.teardown()
