import yaml
import argparse
from lib.run import TestDriver 

# parse cli args
parser = argparse.ArgumentParser(description='Sequoia Test Driver')
parser.add_argument("--scope",  help="scope file", required=True)
parser.add_argument("--test",  help="test file", required=True)
args = parser.parse_args()

# read config files
stream = open(args.scope, "r")
scope = yaml.load(stream)
stream = open(args.test, "r")
test = yaml.load(stream)

# test
test_driver = TestDriver(scope, test)
test_driver.run()
