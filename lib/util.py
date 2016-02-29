import yaml

stream = open(args.scope, "r")
SCOPE = yaml.load(stream)
stream = open(args.test, "r")

