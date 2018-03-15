import paramiko
import sys
import select
from threading import Thread


class CBInit():
    def run(self):
        if len(sys.argv) < 5:
            raise Exception("This script expects min 4 arguments ")

        self.hostname = sys.argv[1]
        self.sshusername = sys.argv[2]
        self.sshpassword = sys.argv[3]
        self.operation = sys.argv[4]
        version,err=self.execute_command("cat /etc/*release | grep -w NAME=")

        if self.operation == "start":
            if version[0].__contains__("CentOS Linux"):
                self.command="systemctl start couchbase-server.service"
            elif version[0].__contains__("Ubuntu"):
                self.command="service couchbase-server start"
        elif self.operation == "stop":
            if version[0].__contains__("CentOS Linux"):
                self.command="systemctl stop couchbase-server.service"
            elif version[0].__contains__("Ubuntu"):
                self.command="service couchbase-server stop"
        self.execute_command(self.command)

    def run_parallel(self):
        self.hostname = sys.argv[1]
        ips=self.hostname.split(',')
        threads = []
        for i in range(len(ips)):
            host=ips[i]
            threads.append(Thread(target=self.create_command, args=(host,)))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def create_command(self, ip):
        self.sshusername = sys.argv[2]
        self.sshpassword = sys.argv[3]
        self.operation = sys.argv[4]
        version, err = self.execute_command("cat /etc/*release | grep -w NAME=",ip)

        if self.operation == "start":
            if version[0].__contains__("CentOS Linux"):
                self.command = "systemctl start couchbase-server.service"
            elif version[0].__contains__("Ubuntu"):
                self.command = "service couchbase-server start"
        elif self.operation == "stop":
            if version[0].__contains__("CentOS Linux"):
                self.command = "systemctl stop couchbase-server.service"
            elif version[0].__contains__("Ubuntu"):
                self.command = "service couchbase-server stop"
        self.execute_command(self.command,ip)

    def execute_command(self, command,host):

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=self.sshusername, password=self.sshpassword)

        print "Executing : {0}".format(command)
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)

        output = ""
        while not ssh_stdout.channel.exit_status_ready():
            # Only print data if there is data to read in the channel
            if ssh_stdout.channel.recv_ready():
                rl, wl, xl = select.select([ssh_stdout.channel], [], [], 0.0)
                if len(rl) > 0:
                    tmp = ssh_stdout.channel.recv(1024)
                    output += tmp.decode()

        output = output.split("\n")
        for i in range(len(output)):
            print output[i]

        ssh.close()

        return output, ssh_stderr


if __name__ == '__main__':
    CBInit().run_parallel()