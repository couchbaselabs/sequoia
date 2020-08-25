import base64
import sys
import os
from datetime import datetime
import httplib2
import json
import time


class EventingOperations():
    def run(self):
        if len(sys.argv) < 7:
            raise Exception("This script expects min 6 arguments")

        self.hostname = sys.argv[1]
        self.port = sys.argv[2]
        self.app_filename = sys.argv[3]
        self.username = sys.argv[4]
        self.password = sys.argv[5]
        self.operation = sys.argv[6]
        self.dump_stats = False
        if len(sys.argv) > 7:
            self.dump_stats = bool(sys.argv[7])

        if self.operation=="wait_for_failover":
            self.wait_for_failover_complete()
        else:
            # read appcode from file
            app_definition = self.read_function_definition_from_file(
                self.app_filename)

            response = self.perform_eventing_lifecycle_operation(app_definition)
            if response:
                print "Eventing lifecycle operation completed successfully"

    def read_function_definition_from_file(self, filename):
        script_dir = os.path.dirname(__file__)
        abs_file_path = os.path.join(script_dir, filename)
        fh = open(abs_file_path, "r")

        app_definition = json.loads(fh.read())
        fh.close()

        print "App definition :\n"
        print app_definition
        return app_definition

    def perform_eventing_lifecycle_operation(self, app_definition):
        appname = app_definition['appname']

        if self.operation == "create_and_deploy":
            status, content, header=self.create_deploy(app_definition)
            if not status:
                print status, content, header
                raise Exception("Failed to deploy application")

            #self.check_deployment_status(appname)
            self.check_handler_status(appname, "deployed")

        elif self.operation == "deploy":
            status, content, header = self.deploy(appname)
            if not status:
                print status, content, header
                raise Exception("Failed to deploy application")

            self.check_handler_status(appname, "deployed")

        elif self.operation == "undeploy":

            # Write stats to file before undeploying
            if self.dump_stats:
                self.write_stats_to_diagnostics_bucket()

            status, content, header = self.undeploy(appname)
            if not status:
                print status, content, header
                raise Exception("Failed to undeploy application")

            self.check_handler_status(appname, "undeployed")

        elif self.operation == "pause":
            status, content, header = self.pause(appname)
            if not status:
                print status, content, header
                raise Exception("Failed to deploy application")
            self.check_handler_status(appname,"paused")

        elif self.operation == "resume":
            status, content, header = self.resume(appname)
            if not status:
                print status, content, header
                raise Exception("Failed to deploy application")

            self.check_handler_status(appname, "deployed")

        elif self.operation == "delete":
            status, content, header = self.delete(appname)
            if not status:
                print status, content, header
                raise Exception("Failed to delete application")
            self.is_handler_present(appname)

        else:
            raise Exception("Invalid operation")

        return True

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

    def write_stats_to_diagnostics_bucket(self):

        stats_url = "http://" + self.hostname + ":8096/api/v1/stats"

        http = httplib2.Http(timeout=120)
        authorization = base64.encodestring(
            '%s:%s' % (self.username, self.password))
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Authorization': 'Basic %s' % authorization}

        # fetch  stats
        stats_response, stats_content = http.request(stats_url, headers=headers)

        # write to bucket
        docid = datetime.now().strftime('%Y%m%d%H%M%S')
        stats = {}
        stats["stats"] = json.loads(stats_content)
        stats["timestamp"] = str(datetime.now())
        diagnostics_bucket_url = "http://" + self.hostname + ":8091"+ "/pools/default/buckets/test_diagnostics/docs/" + docid

        response, content = http.request(diagnostics_bucket_url, "POST",
                                         "value=" + json.dumps(stats,indent=4, separators=(',', ': ')), headers)
        print response,content

    def _http_request(self, appname, method, eventing_endpoint, app_definition,
                      timeout=120):
        authorization = base64.encodestring(
            '%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json',
                   'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/_p/event/" + eventing_endpoint + "/?name=" + appname

        if method != "DELETE":
            response, content = httplib2.Http(timeout=timeout).request(url,
                                                                       method,
                                                                       json.dumps(
                                                                           app_definition).encode(
                                                                           "ascii",
                                                                           "ignore"),
                                                                       headers)
        else:
            response, content = httplib2.Http(timeout=timeout).request(uri=url,
                                                                       method=method,
                                                                       headers=headers)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def _http_request_public(self, appname, method, eventing_endpoint, app_definition,
                      timeout=120):
        authorization = base64.encodestring(
            '%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json',
                   'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/api/v1/functions/" + appname

        if method != "DELETE":
            response, content = httplib2.Http(timeout=timeout).request(url,
                                                                       method,
                                                                       json.dumps(
                                                                           app_definition).encode(
                                                                           "ascii",
                                                                           "ignore"),
                                                                       headers)
        else:
            response, content = httplib2.Http(timeout=timeout).request(uri=url,
                                                                       method=method,
                                                                       headers=headers)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response



    def check_deployment_status(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "http://" + self.hostname + ":8091" + "/_p/event/getDeployedApps"
        method="GET"

        response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
        result=json.loads(content)
        status=response['status']
        if not status:
            print status, result, headers
            raise Exception("Failed to get deployed apps")
        count = 0
        while appname not in result:
            time.sleep(30)
            count += 1
            response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
            result = json.loads(content)
        # if count == 20:
        #     raise Exception(
        #         'Eventing took lot of time to come out of bootstrap state or did not successfully bootstrap')

    def check_undeployment_status(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "http://" + self.hostname + ":8091" + "/_p/event/getRunningApps"
        method="GET"

        response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
        result=json.loads(content)
        status=response['status']
        if not status:
            print status, result, headers
            raise Exception("Failed to get deployed apps")
        count = 0
        while appname in result:
            time.sleep(30)
            count += 1
            response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
            result = json.loads(content)
        # if count == 20:
        #     raise Exception(
        #         'Eventing took lot of time to undeploy')

    def deploy(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/api/v1/functions/" + appname +"/settings"
        body="{\"deployment_status\":true,\"processing_status\":true,\"dcp_stream_boundary\":\"from_now\"}"
        response, content = httplib2.Http(timeout=120).request(uri=url, method="POST", headers=headers,body=body)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def pause(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/api/v1/functions/" + appname +"/settings"
        body="{\"deployment_status\":true,\"processing_status\":false}"
        response, content = httplib2.Http(timeout=120).request(uri=url, method="POST", headers=headers,body=body)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def resume(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/api/v1/functions/" + appname +"/settings"
        body="{\"deployment_status\":true,\"processing_status\":true}"
        response, content = httplib2.Http(timeout=120).request(uri=url, method="POST", headers=headers,body=body)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def check_handler_status(self,appname,app_status):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "http://" + self.hostname + ":8091" + "/_p/event/api/v1/status"
        method="GET"

        response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
        result=json.loads(content)
        status=response['status']
        if not status:
            print status, result, headers
            raise Exception("Failed to get deployed apps")
        composite_status = None
        while composite_status != app_status:
            time.sleep(10)
            response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
            result = json.loads(content)
            for i in range(len(result['apps'])):
                if result['apps'][i]['name']== appname:
                    composite_status = result['apps'][i]['composite_status']

    def is_handler_present(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "http://" + self.hostname + ":8091" + "/_p/event/api/v1/status"
        method="GET"

        response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
        result=json.loads(content)
        status=response['status']
        if not status:
            print status, result, headers
            raise Exception("Failed to get deployed apps")
        while appname in result:
            time.sleep(10)
            response, content = httplib2.Http(timeout=120).request(uri=url, method=method, headers=headers)
            result = json.loads(content)
        return False

    def create_deploy(self,app_definition):
        app_definition['settings']['processing_status'] = True
        app_definition['settings']['deployment_status'] = True
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}
        url = "http://" + self.hostname + ":8096" + "/api/v1/functions/"
        func=[]
        func.append(app_definition)
        body=json.dumps(func).encode("ascii","ignore")
        response, content = httplib2.Http(timeout=120).request(uri=url, method="POST", headers=headers, body=body)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def undeploy(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/api/v1/functions/" + appname +"/settings"
        body="{\"deployment_status\":false,\"processing_status\":false}"
        response, content = httplib2.Http(timeout=120).request(uri=url, method="POST", headers=headers,body=
                                                                           body)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def delete(self,appname):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/api/v1/functions/" + appname
        response, content = httplib2.Http(timeout=120).request(uri=url, method="DELETE", headers=headers)
        print content, response

        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response

    def failover_rebalance_status(self):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))

        headers = {'Content-type': 'application/json', 'Authorization': 'Basic %s' % authorization}

        url = "http://" + self.hostname + ":" + self.port + "/getAggRebalanceStatus"
        response, content = httplib2.Http(timeout=120).request(uri=url, method="GET", headers=headers)

        if response['status'] in ['200', '201', '202']:
            if content == "true":
                return True, True, response
            else:
                return True, False , response
        else:
            return False, content, response

if __name__ == '__main__':
    EventingOperations().run()
