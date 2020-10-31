import random
import string
import time
from datetime import datetime
import httplib2
import json
from optparse import OptionParser


class CollectionOperations():
    def run(self):
        usage = '''%prog -i hostname:port -u username -p password -b bucket -o operations -s scope_name -c collection_name --count
                 %prog -i hostname:port -u username -p password -b bucket -o operations -s scope_name1,scope_name2 -c collection_name'''
        parser = OptionParser(usage)
        parser.add_option("-i", dest="host", help="server ip with port <ip>:<port>")
        parser.add_option("-u", dest="username", default="Administrator", help="user name default=Administrator")
        parser.add_option("-p", dest="password", default="password", help="password default=password")
        parser.add_option("-b", dest="bucket", default="default", help="bucket, default=default")
        parser.add_option("-o", dest="operations", choices=['get', 'create', 'delete', 'create_multi_scope_collection', 'crud_mode'],
                          help="create or delete scope/collections")
        parser.add_option("-s", dest="scopename", help="scope name")
        parser.add_option("-c", dest="collectionname", help="collection name")
        parser.add_option("--count", dest="count", type="int", default=1,
                          help="count of collection/scope to be created/deleted, default=1")
        parser.add_option("--scope_count", dest="scope_count", type="int", default=1,
                          help="count of scopes to be created in multi-scope/coll operation, default=1")
        parser.add_option("--collection_count", dest="collection_count", type="int", default=1,
                          help="count of scopes to be created in multi-scope/coll operation, default=1")
        parser.add_option("--collection_distribution", dest="collection_distribution", choices=["uniform", "random"],
                          default="uniform", help="Number of collections per scope to be created uniformly/randomly")
        parser.add_option("--max_scopes", dest="max_scopes", type="int", help="Max scopes to be created in CRUD mode", default=10)
        parser.add_option("--max_collections", dest="max_collections", type="int",
                          help="Max collections to be created in CRUD mode", default=100)
        parser.add_option("--crud_timeout", dest="crud_timeout",
                          help="Timeout for CRUD mode (in secs). Default = 0 (infinite)", type="int", default=0)
        parser.add_option("--crud_interval", dest="crud_interval",
                          help="Interval between operations in CRUD mode (in secs). Default = 2 secs", type="int",
                          default=5)

        # parser.add_option("--list",dest="list",type="string",help="list of collections/scope to be deleted")

        options, args = parser.parse_args()
        # print(options)
        self.host = options.host
        self.username = options.username
        self.password = options.password
        self.count = options.count
        # self.list=options.list.split(",")

        if options.host is None or options.operations is None:
            print("Hostname and operations are mandatory")
            parser.print_help()
            exit(1)
        if ":" not in options.host:
            print("pass host with port as ip:port")
            parser.print_help()
            exit(1)
        if options.operations == "create":
            print("create")
            if options.collectionname is None:
                if self.count == 1:
                    self.create_scope(options.bucket, options.scopename)
                else:
                    self.create_multiple_scope(options.bucket, options.scopename, self.count)
            else:
                if self.count == 1:
                    self.create_collection(options.bucket, options.scopename, options.collectionname)
                else:
                    self.create_multiple_collection(options.bucket, options.scopename, options.collectionname,
                                                    self.count)
        elif options.operations == "delete":
            print("delete")
            if options.collectionname is None:
                if "," in options.scopename or self.count == 1:
                    self.delete_scope(options.bucket, options.scopename)
                else:
                    self.delete_multiple_scope(options.bucket, options.scopename, self.count)
            else:
                if "," in options.collectionname or self.count == 1:
                    self.delete_collection(options.bucket, options.scopename, options.collectionname)
                else:
                    self.delete_multiple_collection(options.bucket, options.scopename, options.collectionname,
                                                    self.count)
        elif options.operations == "get":
            self.getallcollections(options.bucket)
        elif options.operations == "create_multi_scope_collection":
            self.create_multi_scopes_collections(options.bucket, options.scope_count, options.collection_count,
                                                 options.scopename, options.collectionname,
                                                 options.collection_distribution)
        elif options.operations == "crud_mode":
            self.crud_on_scope_collections(options.bucket, options.max_scopes, options.max_collections,
                                           options.crud_timeout, options.crud_interval)

    def getallcollections(self, bucket):
        url = bucket + "/collections"
        passed, content, response = self.api_call(url, "GET")
        collection_map = {}
        scopes_dict = content["scopes"]
        for obj in scopes_dict:
            collection_list = obj["collections"]
            coll_list = []
            for obj2 in collection_list:
                coll_list.append(obj2["name"])
            collection_map[obj["name"]] = coll_list
        # print(collection_map)
        print(json.dumps(collection_map, sort_keys=True, indent=4))
        return collection_map

    def get_all_collections_for_scope(self, bucket, scope):
        url = bucket + "/collections"
        passed, content, response = self.api_call(url, "GET")
        collection_map = {}
        coll_list = []
        scopes_dict = content["scopes"]
        for obj in scopes_dict:
            if obj["name"] == scope:
                collection_list = obj["collections"]
                for obj2 in collection_list:
                    coll_list.append(obj2["name"])
            else:
                pass
        return coll_list

    def get_raw_collection_map(self, bucket):
        url = bucket + "/collections"
        passed, content, response = self.api_call(url, "GET")
        return content

    def getallscopes(self, bucket):
        url = bucket + "/collections"
        passed, content, response = self.api_call(url, "GET")
        scopes_list = content["scopes"]
        return scopes_list

    def get_scope_list(self, bucket):
        scope_list = []
        content = self.get_raw_collection_map(bucket)
        #scope_coll_map = self.getallscopes(bucket)
        for scope in content["scopes"]:
            scope_list.append(scope["name"])

        return scope_list

    def create_scope(self, bucket, scope):
        scope_list = scope.split(",")
        for scope in scope_list:
            url = bucket + "/collections"
            scope_body = str("name=" + scope).encode('utf-8')
            passed, response, content = self.api_call(url, "POST", body=scope_body)
            print(response, content)

    def create_multiple_scope(self, bucket, scope, count):
        for i in range(count):
            self.create_scope(bucket, scope + "-" + str(i))

    def create_multi_scopes_collections(self, bucket, scope_count, collection_count, scope_prefix="scope_",
                                        collection_prefix="coll_", collection_distribution="uniform"):
        collections_created = 0
        for i in range(0, scope_count):
            self.create_scope(bucket, scope_prefix + str(i))
            if collection_distribution == "uniform":
                num_collections = (collection_count - collections_created) // (scope_count - i)
            else:
                num_collections = random.randint(
                    int((collection_count - collections_created) // (scope_count - i) * 0.5),
                    int((collection_count - collections_created) // (scope_count - i) * 1.5))

            if collections_created >= collection_count:
                num_collections = 0
            if (collections_created + num_collections) > collection_count:
                num_collections = collection_count - collections_created

            if num_collections > 0:
                self.create_multiple_collection(bucket, scope_prefix + str(i), collection_prefix, num_collections)

            collections_created += num_collections

    def create_collection(self, bucket, scope, collection):
        coll_list = collection.split(",")
        for collection in coll_list:
            url = bucket + "/collections/" + scope
            collection_body = str("name=" + collection).encode('utf-8')
            passed, response, content = self.api_call(url, "POST", body=collection_body)
            print(response, content)

    def create_multiple_collection(self, bucket, scope, collection, count):
        for i in range(count):
            self.create_collection(bucket, scope, collection + "-" + str(i))

    def delete_scope(self, bucket, scope):
        scope_list = scope.split(",")
        for scope in scope_list:
            url = bucket + "/collections/" + scope
            passed, response, content = self.api_call(url, "DELETE")
            print(response, content)

    def delete_multiple_scope(self, bucket, scope_name, count):
        for i in range(count):
            url = bucket + "/collections/" + scope_name + "-" + str(i)
            passed, response, content = self.api_call(url, "DELETE")
            print(response, content)

    def delete_collection(self, bucket, scope, collection):
        coll_list = collection.split(",")
        for collection in coll_list:
            url = bucket + "/collections/" + scope + "/" + collection
            passed, response, content = self.api_call(url, "DELETE")
            print(response, content)

    def delete_multiple_collection(self, bucket, scope, collection_name, count):
        for i in range(count):
            url = bucket + "/collections/" + scope + "/" + collection_name + "-" + str(i)
            passed, response, content = self.api_call(url, "DELETE")
            print(response, content)

    def crud_on_scope_collections(self, bucket, max_scopes=10, max_collections=100, timeout=3600, interval=60):
        # Establish timeout. If timeout > 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        while True:
            random.seed(datetime.now())
            # First get the current count for scopes and collections in the bucket
            curr_scope_list = self.get_scope_list(bucket)
            curr_scope_num = len(curr_scope_list)

            curr_coll_count = 0
            curr_coll_map = {}
            if curr_scope_num > 0:
                #curr_coll_map = self.getallcollections(bucket)
                curr_coll_map = self.get_raw_collection_map(bucket)
                for scope in curr_coll_map["scopes"]:
                    curr_coll_count += len(scope["collections"])

            print("Existing number of scopes = %s, collections = %s" % (curr_scope_num, curr_coll_count))

            # Randomly choose what object has to created/dropped - scope or collection
            random_obj = random.choice(["scope", "collection", "collection", "collection", "collection"])

            # Randomly choose what operation has to be performed on the object : create/drop
            random_operation = random.choice(["create", "drop"])

            # Create / Drop single scope
            if random_obj == "scope":
                if curr_scope_num == 1:
                    operation = "create"
                elif curr_scope_num >= int(max_scopes):
                    operation = "drop"
                else:
                    operation = random_operation

                print("Scope : Operation = %s" % operation)

                if operation == "create":
                    letters_and_digits = string.ascii_letters + string.digits
                    scope_name = ''.join((random.choice(letters_and_digits) for i in range(random.randint(8,30))))
                    print("Creating Scope : %s" % scope_name)
                    self.create_scope(bucket, scope_name)
                else:
                    scope_name = random.choice([x for x in curr_scope_list if x != "_default"])
                    print("Deleting Scope : %s" % scope_name)
                    self.delete_scope(bucket, scope_name)

            # Create / Drop single collection
            else:
                if curr_coll_count == 1:
                    operation = "create"
                elif curr_coll_count >= int(max_collections):
                    operation = "drop"
                else:
                    operation = random_operation

                print ("Collection : Operation = %s" % operation)

                if operation == "create":
                    letters_and_digits = string.ascii_letters + string.digits
                    coll_name = ''.join((random.choice(letters_and_digits) for i in range(random.randint(8,30))))
                    scope = random.choice(curr_scope_list)
                    print("Creating Collection : %s in scope %s" % (coll_name, scope))
                    self.create_collection(bucket, scope, coll_name)
                else:
                    scope = random.choice(curr_scope_list)
                    coll_list = []
                    for sc in curr_coll_map["scopes"]:
                        if sc["name"] == scope:
                            for coll in sc["collections"]:
                                coll_list.append(coll["name"])
                        else:
                            pass
                    if (scope == "_default" and len(coll_list) > 1) or (scope != "_default" and len(coll_list) > 0):
                        coll_name = random.choice([x for x in coll_list if x != "_default"])
                        print("Deleting Collection : %s in scope %s" % (coll_name, scope))
                        self.delete_collection(bucket, scope, coll_name)
                    else:
                        pass

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break

            # Wait for the interval before doing the next CRUD operation
            time.sleep(interval)

    def api_call(self, url, method="GET", body=None):
        # authorization = base64.encodestring(self.username+":"+self.password)

        headers = {'content-type': 'application/x-www-form-urlencoded'}

        url = "http://" + self.host + "/pools/default/buckets/" + url
        http = httplib2.Http(timeout=120)
        http.add_credentials(self.username, self.password)
        response, content = http.request(uri=url, method=method, headers=headers, body=body)
        if response['status'] in ['200', '201', '202']:
            return True, json.loads(content), response
        else:
            return False, content, response


if __name__ == "__main__":
    CollectionOperations().run()
