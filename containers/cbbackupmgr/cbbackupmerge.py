import paramiko
import sys

import select


class CBBackupMerge():
    def run(self):

        if len(sys.argv) != 5:
            raise Exception("This script expects 5 arguments")

        # Hostname : sys.argv[1]
        # SSH Username : sys.argv[2]
        # SSH Password : sys.argv[3]
        # Backup Location : sys.argv[4]

        command = "cd {0}/backup; sleep 1; find . -maxdepth 1 -type d -name [^\.]\* | sed 's:^\./::' | sort".format(sys.argv[4])
        output, std_err = self.execute_command(command)

        try:
            merge_start = output[0]
            merge_end = output[len(output)-2]


            merge_command = "/opt/couchbase/bin/cbbackupmgr merge -a {0} -r backup --start {1} --end {2}".format(sys.argv[4], merge_start, merge_end)
            output,std_err = self.execute_command(merge_command)

            if output[0] != "Merge completed successfully" and std_err:
                raise Exception("cbbackupmgr merge command results in an error : %s", std_err)
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
    CBBackupMerge().run()
