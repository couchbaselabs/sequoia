import base64
import json
import os
import time,re
from optparse import OptionParser
from string import Template

import httplib2
import dns.resolver


class EventingHelper:
    handler_map={"bucket_op":"neo/bucket_op.js","timers":"neo/timers.js","n1ql":"neo/n1ql.js","sbm":"neo/sbm.js","curl":"neo/curl.js","bucket_op_sbm":"neo/bucket_op_sbm.js"}

    def __init__(self):
        self.hostname = None
        self.username = None
        self.password = None
        self.capella_run = False
        self.use_tls = False
        self.use_https = False
        self.eventing_port = 8096
        self.node_port = 8091
        self.n1ql_port = 8093
        self.protocol = "http"
        self.rest_url = None

    def run(self):
        usage = '''%prog -i hostname:port -u username -p password -s source_collection -m metadata_colletcion -d bindings -t type -n number'''
        parser = OptionParser(usage)
        parser.add_option("-i", dest="host", help="server ip with port <ip>:<port>")
        parser.add_option("-u", dest="username", default="Administrator", help="user name default=Administrator")
        parser.add_option("-p", dest="password", default="password", help="password default=password")
        parser.add_option("-s",dest="source",default="_default")
        parser.add_option("-m",dest="metadata")
        parser.add_option("-d",dest="bindings",action="append")
        parser.add_option("-t",dest="type")
        parser.add_option("--name",dest="name")
        parser.add_option("-n",dest="number",type="int", default=1)
        parser.add_option("-o",dest="operation",choices=['create', 'deploy', 'pause', 'resume', 'undeploy', 'delete', 'wait_for_state','verify','wait_for_failover'])
        parser.add_option("--wait",dest="wait",default=False)
        parser.add_option("--state",dest="state")
        parser.add_option("-l",dest="log_level",default="INFO",choices=['INFO','ERROR','WARNING','DEBUG','TRACE'])
        parser.add_option("--timeout",dest="timeout",type="int", default=1200)
        parser.add_option("--sleep",dest="sleep",type="int", default=60)
        parser.add_option("--sbm",dest="sbm",default=False)
        parser.add_option("--capella", dest="capella", help="Set to True if tests need to run on Capella", default=False)
        parser.add_option("--tls", dest="tls", help="Set to True if tests need to run with TLS enabled", default=False)
        options, args = parser.parse_args()
        print(options)
        self.username = options.username
        self.password = options.password
        self.hostname = options.host
        self.use_tls = options.tls
        self.capella_run = options.capella
        self.use_https = self.use_tls or self.capella_run
        if self.use_https:
            self.eventing_port = 18096
            self.node_port = 18091
            self.n1ql_port = 18093
            self.protocol = "https"
            if self.capella_run:
                self.rest_url = self.fetch_rest_url(self.hostname)
            else:
                self.rest_url = self.hostname
        else:
            self.eventing_port = 8096
            self.node_port = 8091
            self.n1ql_port = 8093
            self.protocol = "http"
            self.rest_url = self.hostname
        functions=[]
        if options.operation == "create":
            if options.type != "MIX":
                for i in range(options.number):
                    if options.name ==None:
                        name="handler_"+options.type+"_"+str(i)
                    else:
                        name=options.name+"_"+str(i)
                    handler=self.create_handler(appname=name,options=options)
                    functions.append(handler)
            self.create_save_handler(functions)
        elif options.operation == "deploy":
            self.deploy_handlers(options)
        elif options.operation == "pause":
            self.pause_handler(options)
        elif options.operation == "resume":
            self.resume_handler(options)
        elif options.operation == "undeploy":
            self.undeploy_handler(options)
        elif options.operation == "delete":
            self.delete(options)
        elif options.operation == "wait_for_state":
            if options.name == None:
                handlers = self.get_all_handlers()
            else:
                handlers = self.get_all_handlers(options.name)
            for app in handlers:
                self.check_handler_status(app,options.state)
        elif options.operation == "verify":
            self.verify_doc(options)
        elif options.operation == "wait_for_failover":
            self.wait_for_failover_complete()

    def deploy_handlers(self,options,handler_name=None):
        wait_for_state=options.wait
        if handler_name ==None and options.name==None:
            handlers=self.get_all_handlers()
        elif options.name !=None:
            handlers=self.get_all_handlers(options.name)
        else:
            handlers=[handler_name]
        print(handlers)
        for handler in handlers:
            print("deploying : "+handler)
            self.perform_lifecycle_operation(handler,"deploy")
            if wait_for_state:
                self.check_handler_status(handler,"deployed")
                print(handler," Deployed successfully")

    def pause_handler(self,options,handler_name=None):
        wait_for_state = options.wait
        if handler_name ==None and options.name==None:
            handlers=self.get_all_handlers()
        elif options.name !=None:
            handlers=self.get_all_handlers(options.name)
        else:
            handlers=[handler_name]
        print(handlers)
        for handler in handlers:
            print("pausing : "+handler)
            self.perform_lifecycle_operation(handler,"pause")
            if wait_for_state:
                self.check_handler_status(handler,"paused")
                print(handler," Deployed successfully")

    def resume_handler(self,options,handler_name=None):
        wait_for_state = options.wait
        if handler_name ==None and options.name==None:
            handlers=self.get_all_handlers()
        elif options.name !=None:
            handlers=self.get_all_handlers(options.name)
        else:
            handlers=[handler_name]
        print(handlers)
        for handler in handlers:
            print("resuming : "+handler)
            self.perform_lifecycle_operation(handler,"resume")
            if wait_for_state:
                self.check_handler_status(handler,"deployed")
                print(handler," Deployed successfully")

    def undeploy_handler(self,options,handler_name=None):
        wait_for_state = options.wait
        if handler_name ==None and options.name==None:
            handlers=self.get_all_handlers()
        elif options.name !=None:
            handlers=self.get_all_handlers(options.name)
        else:
            handlers=[handler_name]
        print(handlers)
        for handler in handlers:
            print("undeploying : "+handler)
            self.perform_lifecycle_operation(handler,"undeploy")
            if wait_for_state:
                self.check_handler_status(handler,"undeployed")
                print(handler," Deployed successfully")

    def delete(self,options):
        if options.name==None:
            print("deleting all handlers ")
            self.delete_handlers()
        elif options.name != None:
            handlers = self.get_all_handlers(options.name)
            print("deleting : "+str(handlers))
            for handler in handlers:
                self.delete_handlers(handler)


    def get_all_handlers(self,prefix=None):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "{0}://{1}:{2}/api/v1/list/functions".format(self.protocol, self.rest_url, self.eventing_port)
        response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="GET", headers=headers)
        print(content, response)
        if response.status != 200:
            raise Exception(content)
        result = json.loads(content)
        if prefix == None:
            return result["functions"]
        else:
            return self.fillter_handler(result["functions"],prefix)

    def create_save_handler(self,functions):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "{0}://{1}:{2}/api/v1/functions/".format(self.protocol, self.rest_url, self.eventing_port)
        print(url)
        body = json.dumps(functions).encode("ascii", "ignore")
        response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="POST", headers=headers, body=body)
        print(content, response)
        if response.status !=200:
            raise Exception(content)

    def perform_lifecycle_operation(self, name, operation,body=None):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "{0}://{1}:{2}/api/v1/functions/{3}/{4}".format(self.protocol, self.rest_url, self.eventing_port, name, operation)
        try:
            if body !=None:
                body = json.dumps(body).encode("ascii", "ignore")
                response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="POST", headers=headers, body=body)
            else:
                response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="POST", headers=headers)
            print(content, response)
            if response.status !=200:
                raise Exception(content)
        except Exception as e:
            raise e

    def create_handler(self,appname,options,dcp_stream_boundary="everything"):
        appcode=self.handler_map[options.type]
        source_binding=options.source
        metadata_binding=options.metadata
        destination_bindings=options.bindings
        body = {}
        body['appname'] = appname
        script_dir = os.path.dirname(__file__)
        abs_file_path = os.path.join(script_dir, appcode)
        fh = open(abs_file_path, "r")
        body['appcode'] = fh.read()
        fh.close()
        body['depcfg'] = {}
        meta=metadata_binding.split(".")
        src=source_binding.split(".")
        body['depcfg']['metadata_bucket'] = meta[0]
        body['depcfg']['metadata_scope'] = meta[1]
        body['depcfg']['metadata_collection'] = meta[2]
        body['depcfg']['source_bucket'] = src[0]
        body['depcfg']['source_scope'] = src[1]
        body['depcfg']['source_collection'] = src[2]
        body['depcfg']['buckets'] = []
        body['depcfg']['curl'] = []
        if options.type !='n1ql':
            for binding in destination_bindings:
                bind_map=binding.split(".")
                if  len(bind_map)< 5:
                    raise Exception("Binding {} doesn't have all the fields".format(binding))
                body['depcfg']['buckets'].append(
                    {"alias": bind_map[0], "bucket_name": bind_map[1], "scope_name": bind_map[2],
                     "collection_name": bind_map[3], "access": bind_map[4]})
        else:
            bind= destination_bindings[0].split(".")
            collection = bind[1] + "." + bind[2] + ".`" + bind[3] + "`"
            body['appcode']=Template(body['appcode']).substitute(namespace=collection.strip())
        body['settings'] = {}
        body['settings']['dcp_stream_boundary'] = dcp_stream_boundary
        body['settings']['deployment_status'] = False
        body['settings']['processing_status'] = False
        if options.type == 'timers':
            body['settings']['worker_count'] = 3
        else:
            body['settings']['worker_count'] = 1
        body['settings']['log_level'] = options.log_level
        if options.type=='curl':
            body['depcfg']['curl'].append({"hostname": "http://qa.sc.couchbase.com/", "value": "server","auth_type":'no-auth',
                                          "allow_cookies": True, "validate_ssl_certificate": True})
        body['function_scope'] = {"bucket": "*", "scope": "*"}
        print(body)
        return body

    def check_handler_status(self,appname,app_status):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "{0}://{1}:{2}/api/v1/status/{3}".format(self.protocol, self.rest_url, self.eventing_port, appname)
        method="GET"
        response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method=method, headers=headers)
        print("v1/status {}".format(content))
        result=json.loads(content)
        status=response['status']
        if not status:
            print(status, result, headers)
            raise Exception("Failed to get deployed apps")
        composite_status = None
        while composite_status != app_status:
            try:
                print("checking {} for {}".format(app_status,appname))
                time.sleep(5)
                response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method=method, headers=headers)
                result = json.loads(content)
                composite_status = result['app']['composite_status']
            except Exception as e:
                print(e)

    def delete_handlers(self,handler=None):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        if handler!=None:
            url = "{0}://{1}:{2}/api/v1/functions/{3}".format(self.protocol, self.rest_url, self.eventing_port, handler)
        else:
            url = "{0}://{1}:{2}/api/v1/functions/".format(self.protocol, self.rest_url, self.eventing_port)
        response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="DELETE", headers=headers)
        print(content, response)
        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def execute_n1ql_query(self,query):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic %s' % authorization}
        url = "{0}://{1}:{2}/query/service".format(self.protocol, self.rest_url, self.n1ql_port)
        body="statement="+query
        response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="POST", headers=headers,body=body)
        if response.status != 200:
            print(content, response)
            raise Exception(content)
        return json.loads(content)

    def fillter_handler(self,handlers,prefix):
        return [str for str in handlers if prefix in str]

    def verify_doc(self, options):
        source_collection=options.source
        destination_collection=options.bindings
        source_query="select raw count(*) from "+str(source_collection)
        dst_query = "select raw count(*) from "+str(destination_collection[0])
        source_count=self.execute_n1ql_query(source_query)
        binding_count=self.execute_n1ql_query(dst_query)
        curr_count = 0
        expected_count = (options.timeout / options.sleep)
        while curr_count < expected_count:
            if source_count["results"][0] == binding_count["results"][0] and not options.sbm:
                break
            elif 2*source_count["results"][0] == binding_count["results"][0] and options.sbm:
                break
            print("No of docs in source and destination : Source Bucket({0}) : {1}, Destination Bucket({2}) : {3}".format(
                    source_collection, source_count["results"][0], destination_collection, binding_count["results"][0]))
            time.sleep(options.sleep)
            curr_count += 1
            source_count = self.execute_n1ql_query(source_query)
            binding_count = self.execute_n1ql_query(dst_query)
        if source_count["results"][0] == binding_count["results"][0]:
            print("No of docs in source and destination match: Source Bucket({0}) : {1}, Destination Bucket({2}) : {3}".
                  format(source_collection, source_count["results"][0], destination_collection, binding_count["results"][0]))
        if options.sbm and binding_count["results"][0] == 2*source_count["results"][0]:
            print(
                "No of docs for source bucket mutation match for sbm: Source Bucket({0}) : {1}, Destination Bucket({2}) : {3}".format(
                    source_collection, source_count["results"][0], destination_collection, binding_count["results"][0]))
        elif curr_count >= expected_count:
            raise Exception("No of docs in source and destination don't match: Source Bucket({0}) : {1}, Destination Bucket({2}): {3}".
            format(source_collection, source_count["results"][0], destination_collection, binding_count["results"][0]))

    def wait_for_failover_complete(self):
        status, content, header = self.failover_rebalance_status()
        count = 0
        ### wait for 5 min max
        while not content:
            status, content, header = self.failover_rebalance_status()
            count = count + 1
            time.sleep(1)
            if count >= 300:
                raise Exception("Failover not started even after waiting for long")
        print("##### Failover started ######")
        while content:
            status, content, header = self.failover_rebalance_status()
            count = count + 1
            time.sleep(1)
            print("waiting for failover to complete....")
        print("##### Failover Completed #####")

    def failover_rebalance_status(self):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')
        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "{0}://{1}:{2}/getAggRebalanceStatus".format(self.protocol, self.rest_url, self.node_port)
        response, content = httplib2.Http(timeout=120, disable_ssl_certificate_validation=True).request(uri=url, method="GET", headers=headers)
        if response['status'] in ['200', '201', '202']:
            if content == "true":
                return True, True, response
            else:
                return True, False , response
        else:
            return False, content, response

    def fetch_rest_url(self, url):
        """
        meant to find the srv record for Capella runs
        """
        print("This is a Capella run. Finding the srv domain for {}".format(url))
        srv_info = {}
        srv_records = dns.resolver.query('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        print("This is a Capella run. Srv info {}".format(srv_info))
        return srv_info['host']

if __name__ == "__main__":
    EventingHelper().run()