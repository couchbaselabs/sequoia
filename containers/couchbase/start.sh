nohup ./entrypoint.sh couchbase-server &
nohup tail -F /opt/couchbase/var/lib/couchbase/logs/debug.log
/usr/sbin/sshd -D
