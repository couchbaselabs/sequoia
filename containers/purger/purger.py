import os
import sys
import time
import requests
from couchbase.bucket import Bucket
from threading import Thread

SDK_HOST_ARG = sys.argv[1]
VIEW_HOST_ARG = sys.argv[2]
BUCKET_ARG = sys.argv[3]
HOST = SDK_HOST_ARG
VIEW_API="http://"+VIEW_HOST_ARG

def getReq(url, timeout=10):
    rc = None
    try:
       rc = requests.get(url, timeout=timeout)
    except Exception as ex:
       print ex
    return rc


def purge(bucket, ddoc):


    client = Bucket(HOST+'/'+bucket)

    DDOC='/'.join([VIEW_API,bucket,'_design',ddoc,'_view'])
    CLIENTS_Q = DDOC+"/clients?stale=ok&limit=500&group=true"
    print CLIENTS_Q
    # purger for all platforms+comonent combo of each build
    r = getReq(CLIENTS_Q)
    if r is None:
        return

    data = r.json()
    th = []
    for row in data['rows']:
        prefix = row['key']
        low = row['value']['min']
        high = row['value']['max']
        t = Thread(target = delete_keys, args = (bucket, prefix, low, high))
        t.start()
        th.append(t)

    for i in xrange(len(th)):
        th[i].join()

def delete_keys(bucket, prefix, low, high):

    client = Bucket(HOST+'/'+bucket)
    deleted = 0
    failed = 0
    for i in xrange(low, high):
        key = prefix +"_"+str(i)
        try:
            client.delete(key)
            deleted = deleted+1 
        except Exception as ex:
            failed = failed+1 
            pass
    print "Deleted " + str(deleted) + " keys.  Missed " + str(failed)

if __name__ == "__main__":
    offset = 0
    while True:
        try:
            purge(BUCKET_ARG, "purger")
        except Exception as ex:
            print ex
            pass

        print "Last run " + time.strftime("%c")
