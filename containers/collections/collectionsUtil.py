import httplib2
import json
from optparse import OptionParser

class CollectionOperations():
    def run(self):
        usage = '''%prog -i hostname:port -u username -p password -b bucket -o operations -s scope_name -c collection_name --count
                 %prog -i hostname:port -u username -p password -b bucket -o operations -s scope_name1,scope_name2 -c collection_name'''
        parser = OptionParser(usage)
        parser.add_option("-i",dest="host",help="server ip with port <ip>:<port>")
        parser.add_option("-u",dest="username",default="Administrator",help="user name default=Administrator")
        parser.add_option("-p",dest="password",default="password",help="password default=password")
        parser.add_option("-b",dest="bucket",default="default",help="bucket, default=default")
        parser.add_option("-o",dest="operations",choices=['get','create','delete'],help="create or delete scope/collections")
        parser.add_option("-s",dest="scopename",help="scope name")
        parser.add_option("-c",dest="collectionname",help="collection name")
        parser.add_option("--count",dest="count",type="int",default=1,help="count of collection/scope to be created/deleted, default=1")
        #parser.add_option("--list",dest="list",type="string",help="list of collections/scope to be deleted")

        options, args = parser.parse_args()
        #print(options)
        self.host=options.host
        self.username=options.username
        self.password=options.password
        self.count=options.count
        #self.list=options.list.split(",")

        if options.host is None or options.operations is None:
            print("Hostname and operations are mandatory")
            parser.print_help()
            exit(1)
        if ":" not in options.host:
            print("pass host with port as ip:port")
            parser.print_help()
            exit(1)
        if options.operations =="create":
            print("create")
            if options.collectionname is None:
                if self.count==1:
                    self.create_scope(options.bucket,options.scopename)
                else:
                    self.create_multiple_scope(options.bucket,options.scopename,self.count)
            else:
                if self.count==1:
                    self.create_collection(options.bucket,options.scopename,options.collectionname)
                else:
                    self.create_multiple_collection(options.bucket,options.scopename,options.collectionname,self.count)
        elif options.operations =="delete":
            print("delete")
            if options.collectionname is None:
                if "," in options.scopename or self.count==1:
                    self.delete_scope(options.bucket,options.scopename)
                else:
                    self.delete_multiple_scope(options.bucket,options.scopename,self.count)
            else:
                if "," in options.collectionname or self.count==1:
                    self.delete_collection(options.bucket,options.scopename,options.collectionname)
                else:
                    self.delete_multiple_collection(options.bucket,options.scopename,options.collectionname,self.count)
        elif options.operations =="get":
            self.getallcollections(options.bucket)

    def getallcollections(self,bucket):
        url=bucket+"/collections"
        passed, content, response=self.api_call(url,"GET")
        collection_map={}
        scopes_dict=content["scopes"]
        for obj in scopes_dict:
            collection_list=obj["collections"]
            coll_list=[]
            for obj2 in collection_list:
                coll_list.append(obj2["name"])
            collection_map[obj["name"]]=coll_list
        #print(collection_map)
        print(json.dumps(collection_map, sort_keys=True,indent=4))
        return collection_map

    def create_scope(self,bucket,scope):
        scope_list=scope.split(",")
        for scope in scope_list:
            url=bucket+"/collections"
            scope_body=str("name="+scope).encode('utf-8')
            passed,response,content=self.api_call(url,"POST",body=scope_body)
            print(response,content)
    
    def create_multiple_scope(self,bucket,scope,count):
        for i in range(count):
            self.create_scope(bucket,scope+"-"+str(i))

    def create_collection(self,bucket,scope,collection):
        coll_list=collection.split(",")
        for collection in coll_list:
            url=bucket+"/collections/"+scope
            collection_body=str("name="+collection).encode('utf-8')
            passed,response,content=self.api_call(url,"POST",body=collection_body)
            print(response,content)

    def create_multiple_collection(self,bucket,scope,collection,count):
        for i in range(count):
            self.create_collection(bucket,scope,collection+"-"+str(i))

    def delete_scope(self,bucket,scope):
        scope_list=scope.split(",")
        for scope in scope_list:
            url=bucket+"/collections/"+scope
            passed,response,content=self.api_call(url,"DELETE")
            print(response,content)

    def delete_multiple_scope(self,bucket,scope_name,count):
        for i in range(count):
            url=bucket+"/collections/"+scope_name+"-"+str(i)
            passed,response,content=self.api_call(url,"DELETE")
            print(response,content)

    def delete_collection(self,bucket,scope,collection):
        coll_list=collection.split(",")
        for collection in coll_list:
            url=bucket+"/collections/"+scope+"/"+collection
            passed,response,content=self.api_call(url,"DELETE")
            print(response,content)

    def delete_multiple_collection(self,bucket,scope,collection_name,count):
        for i in range(count):
            url=bucket+"/collections/"+scope+"/"+collection_name+"-"+str(i)
            passed,response,content=self.api_call(url,"DELETE")
            print(response,content)

    def api_call(self,url,method="GET",body=None):
        #authorization = base64.encodestring(self.username+":"+self.password)

        headers = {'content-type': 'application/x-www-form-urlencoded'}

        url = "http://" +self.host+"/pools/default/buckets/"+ url
        http=httplib2.Http(timeout=120)
        http.add_credentials(self.username, self.password)
        response, content = http.request(uri=url, method=method, headers=headers,body=body)
        if response['status'] in ['200', '201', '202']:
            return True, json.loads(content), response
        else:
            return False, content, response

if __name__ == "__main__":
    CollectionOperations().run()
