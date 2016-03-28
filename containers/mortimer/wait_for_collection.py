import sys
import time
import requests

av = sys.argv
host = av[1]
user = av[2]
password = av[3]

allCollected = False
while not allCollected:
    r = requests.get('http://'+host+':8091/pools/default/tasks', auth=(user, password))
    if r.status_code == 200:
        tasks = r.json()
        for t in tasks:
            if t['type'] == 'clusterLogsCollection':
                perNode = t['perNode']
                allCollected = all([perNode[n]['status'] == 'collected' for n in perNode])
                if not allCollected:
                    print "Waiting for all node collection to finish..."
                    time.sleep(5)
                else:
                    print "Collection done!"
    else:
        print "Collection failed with status: "+str(r.status_code)
        sys.exit(1)
        break
