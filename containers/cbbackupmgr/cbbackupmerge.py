import paramiko
import sys

import select


class CBBackupMerge():
    def run(self):

        if len(sys.argv) != 6:
            raise Exception("This script expects 5 arguments: hostname, ssh_username, ssh_password, backup_location, repo_name")

        # Hostname : sys.argv[1]
        # SSH Username : sys.argv[2]
        # SSH Password : sys.argv[3]
        # Backup Location : sys.argv[4]
        # Repo Name : sys.argv[5]

        command = "cd {0}/{1}; sleep 1; find . -maxdepth 1 -type d -name [^\.]\* | sed 's:^\./::' | grep -v '^logs$' | sort".format(sys.argv[4], sys.argv[5])
        output, std_err = self.execute_command(command)

        try:
            merge_start = output[0]
            merge_end = output[-1]


            merge_command = "/opt/couchbase/bin/cbbackupmgr merge -a {0} -r {1} --start {2} --end {3}".format(sys.argv[4], sys.argv[5], merge_start, merge_end)
            output,std_err = self.execute_command(merge_command)

            stderr_content = std_err.read().decode().strip() if std_err else ""
            if len(output) > 0 and output[0] != "Merge completed successfully" and stderr_content:
                raise Exception("cbbackupmgr merge command results in an error : %s" % stderr_content)
        except Exception as e:
            raise Exception(str(e))

    def execute_command(self, command):

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(sys.argv[1], username=sys.argv[2], password=sys.argv[3])

        print("Executing : {0}".format(command))
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)

        output = ""
        while not ssh_stdout.channel.exit_status_ready():
            # Only print data if there is data to read in the channel
            if ssh_stdout.channel.recv_ready():
                rl, wl, xl = select.select([ssh_stdout.channel], [], [], 0.0)
                if len(rl) > 0:
                    tmp = ssh_stdout.channel.recv(1024)
                    output += tmp.decode()

        output = output.strip().split("\n")
        for i in range(len(output)):
            print(output[i])

        ssh.close()

        return output, ssh_stderr

if __name__ == '__main__':
    CBBackupMerge().run()
