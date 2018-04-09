import base64
import sys
import httplib2
import json
import time


class EventingDataValidator():
    def run(self):
        if len(sys.argv) < 9:
            raise Exception("This script expects min 8 arguments")
        self.hostname = sys.argv[1]
        self.username = sys.argv[2]
        self.password = sys.argv[3]
        self.src_bucket = sys.argv[4]
        self.dst_bucket = sys.argv[5]
        self.timeout = int(sys.argv[6])
        self.step_sleep = int(sys.argv[7])
        self.croak_on_mismatch = sys.argv[8]
        src_bucket_docs = self.get_bucket_count(bucket=self.src_bucket)
        dst_bucket_docs = self.get_bucket_count(bucket=self.dst_bucket)
        curr_count = 0
        expected_count = (self.timeout / self.step_sleep)
        while dst_bucket_docs != src_bucket_docs and curr_count < expected_count:
            print(
                "No of docs in source and destination : Source Bucket({0}) : {1}, Destination Bucket({2}) : {3}".format(
                    self.src_bucket, src_bucket_docs, self.dst_bucket, dst_bucket_docs))
            time.sleep(self.step_sleep)
            curr_count += 1
            src_bucket_docs = self.get_bucket_count(bucket=self.src_bucket)
            dst_bucket_docs = self.get_bucket_count(bucket=self.dst_bucket)
        if curr_count >= expected_count:
            if self.croak_on_mismatch == "True":
                raise Exception(
                    "No of docs in source and destination don't match: Source Bucket({0}) : {1}, Destination Bucket({2})"
                    " : {3}".format(self.src_bucket, src_bucket_docs, self.dst_bucket, dst_bucket_docs))
            else:
                print(
                    "No of docs in source and destination don't match: Source Bucket({0}) : {1}, Destination Bucket({2})"
                    " : {3}".format(self.src_bucket, src_bucket_docs, self.dst_bucket, dst_bucket_docs))
        if dst_bucket_docs == src_bucket_docs:
            print("No of docs in source and destination match: Source Bucket({0}) : {1}, Destination Bucket({2}) : {3}".
                  format(self.src_bucket, src_bucket_docs, self.dst_bucket, dst_bucket_docs))

    def get_bucket_count(self, bucket='default'):
        stats = {}
        status, json_parsed = self.get_bucket_stats_json(bucket)
        if status:
            op = json_parsed["op"]
            samples = op["samples"]
            for stat_name in samples:
                if samples[stat_name]:
                    last_sample = len(samples[stat_name]) - 1
                    if last_sample:
                        stats[stat_name] = samples[stat_name][last_sample]
        return stats["curr_items"]

    def get_bucket_stats_json(self, bucket='default'):
        api = "http://" + self.hostname + ":8091/pools/default/buckets/" + bucket + "/stats"
        status, content, header = self._http_request(api, "GET")
        json_parsed = json.loads(content)
        return status, json_parsed

    def _http_request(self, api, method='GET', params='', timeout=120):
        authorization = base64.encodestring('%s:%s' % (self.username, self.password))
        headers = {'Content-type': 'application/json',
                   'Authorization': 'Basic %s' % authorization}
        response, content = httplib2.Http(timeout=timeout).request(api, method, params, headers)
        # print content, response
        if response['status'] in ['200', '201', '202']:
            return True, content, response
        else:
            return False, content, response



if __name__ == '__main__':
    EventingDataValidator().run()

