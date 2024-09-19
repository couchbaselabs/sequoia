import time

import paramiko
import sys
import select
from threading import Thread


class CBInit:
    def __init__(self):
        if len(sys.argv) < 5:
            raise Exception("This script expects min 4 arguments ")
        self.hostname = sys.argv[1]
        self.ssh_username = sys.argv[2]
        self.ssh_password = sys.argv[3]
        self.operation = sys.argv[4]

    def run(self):
        version, err = self.execute_command("cat /etc/*release | grep -w NAME=", self.hostname)
        print("OS version output {}. Error {}".format(version, err))
        if self.operation == "start":
            if version.__contains__("CentOS Linux") or version.__contains__("Debian"):
                command = "systemctl start couchbase-server.service"
            elif version.__contains__("Ubuntu"):
                command = "service couchbase-server start"
        elif self.operation == "stop":
            if version.__contains__("CentOS Linux") or version.__contains__("Debian"):
                command = "systemctl stop couchbase-server.service"
            elif version.__contains__("Ubuntu"):
                command = "service couchbase-server stop"
        self.execute_command(command, self.hostname)

    def run_parallel(self):
        self.hostname = sys.argv[1].rstrip("")
        ips = self.hostname.split(',')
        threads = []
        for i in range(len(ips)):
            host = ips[i]
            threads.append(Thread(target=self.create_command, args=(host,)))
        for thread in threads:
            thread.start()
        time.sleep(30)
        for thread in threads:
            thread.join()

    def create_command(self, ip):
        command = None
        version, err = self.execute_command("cat /etc/*release | grep -w NAME=", ip)
        if self.operation == "start":
            if version[0].__contains__("CentOS Linux") or version[0].__contains__("Debian"):
                command = "systemctl start couchbase-server.service"
            elif version[0].__contains__("Ubuntu"):
                command = "service couchbase-server start"
        elif self.operation == "stop":
            if version[0].__contains__("CentOS Linux") or version[0].__contains__("Debian"):
                command = "systemctl stop couchbase-server.service"
            elif version[0].__contains__("Ubuntu"):
                command = "service couchbase-server stop"
        else:
            raise Exception("Operation has to be start or stop")
        self.execute_command(command, ip)

    def execute_command(self, command, host):

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.load_system_host_keys()
        ssh.connect(host, username=self.ssh_username, password=self.ssh_password)
        print("Executing : {0}".format(command))
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)
        ssh_stdout = ssh_stdout.readlines()
        ssh.close()
        output = ssh_stdout[0]
        print(f"Output is {output}")
        return output, ssh_stderr

    def run_commands(self):
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s.load_system_host_keys()
        s.connect(hostname=self.hostname, username=self.ssh_username, password=self.ssh_password)
        command = "cat /etc/*release | grep -w NAME"
        stdin, stdout, stderr = s.exec_command(command)
        stdout = stdout.readlines()
        os_version = stdout[0]
        print("OS is {}".format(os_version))
        flavor = os_version.split("=")[1]
        print("Flavor is {}".format(flavor))
        if "Debian" in flavor or "CentOS" in flavor:
            print("Running Debian/CentOS commands")
            command = "systemctl {} couchbase-server.service".format(self.operation)
        else:
            print("Running Ubuntu commands")
            command = "service couchbase-server {}".format(self.operation)
        stdin, stdout, stderr = s.exec_command(command)
        stdout = stdout.readlines()
        stderr = stderr.readlines()
        print("Couchbase stop/start output is {}. Error is {}".format(stdout, stderr))
        s.close()


if __name__ == '__main__':
    CBInit().run_commands()
