import paramiko
import sys

import select


class CBBackupCompact():
    def run(self):

        if len(sys.argv) != 5:
            raise Exception("This script expects 5 arguments")

        # Hostname : sys.argv[1]
        # SSH Username : sys.argv[2]
        # SSH Password : sys.argv[3]
        # Backup Location : sys.argv[4]

        command = "cd {0}/backup; find . -maxdepth 1 -type d -name [^\.]\* | sed 's:^\./::' | sort".format(sys.argv[4])
        output, std_err = self.execute_command(command)

        try:
            last_backup = output[len(output)-2]

            compact_command = "/opt/couchbase/bin/cbbackupmgr compact -a {0} -r backup --backup {1}".format(sys.argv[4], last_backup)
            output,std_err = self.execute_command(compact_command)

            if "Compaction succeeded" not in output[0] and std_err:
                raise Exception("cbbackupmgr compact command result in an error : %s. Output is : %s" %(std_err, output))
        except Exception as e:
            raise Exception(str(e))

    def execute_command(self, command):

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(sys.argv[1], username=sys.argv[2], password=sys.argv[3])

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
    CBBackupCompact().run()
