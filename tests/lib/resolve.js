var _ = require('lodash')
    , util = require("./util.js").api

var FUNCS = {
    address: function(scope, args, net){
        // address:
        //      resolves server specs to address
        //      of server specified by indexArg
        //
        //      from spec:
        //          -> servers:orchestrator:0:0 
        //          <- scope[servers][0][0].ip
        
        var clusterIndex = parseInt(args[0])
        var nodeIndex = args[1]
        nodeIndex = parseInt(nodeIndex) || 0

        // get cluster name
        var clusterName = _.keys(scope)[clusterIndex]
        var clusterSpec  = {}
        clusterSpec[clusterName] = scope[clusterName]

        // get node name
        var servers = util.extrapolateRange(clusterSpec)
        var serveName = servers[clusterName][nodeIndex]

        // get node address
        var address = net[serveName]
        return address
    },
    clustername: function(scope, args){
        // orchestrator:
        //      resolves server specs to ip
        //      of server specified by indexArg
        //
        //      from spec:
        //          -> servers:clustername:0 
        //          <- scope[servers][0].name
        //

        // get cluster name at requested index
        var clusterIndex = parseInt(args[0])
        var clusterName = _.keys(scope)[clusterIndex]
        return clusterName
    },
    bucketname: function(scope, args){
        // bucketname:
        //      resolves bucketname from scope
        //          -> buckets:bucketname:0:0
        //          <- scope[buckets][0][0].name

        var bucketContextIndex = parseInt(args[0])
        var bucketIndex = args[1]
        bucketIndex = parseInt(bucketIndex) || 0

        // get name of bucket context
        var bucketContextName = _.keys(scope)[bucketContextIndex]
        var bucketSpec  = {}
        bucketSpec[bucketContextName] = scope[bucketContextName]

        // get bucket name
        var buckets = util.extrapolateRange(bucketSpec)
        var bucketName = buckets[bucketContextName][bucketIndex]

        return bucketName
    },
    rest_username: function(scope, args){
        // rest_username:
        //      resolves rest_username for a cluster
        //
        //      from spec:
        //          -> servers:rest_username:0
        //          <- scope[servers][0].rest_username

        // get cluster spec at requested index
        var clusterIndex = parseInt(args[0])
        var clusterName = _.keys(scope)[clusterIndex]
        var clusterSpec = scope[clusterName]
        return clusterSpec.rest_username
    },
    rest_password: function(scope, args){
        // rest_password:
        //      resolves rest_password for a cluster
        //
        //      from spec:
        //          -> servers:rest_password:0
        //          <- scope[servers][0].rest_password

        // get cluster spec at requested index
        var clusterIndex = parseInt(args[0])
        var clusterName = _.keys(scope)[clusterIndex]
        var clusterSpec = scope[clusterName]
        return clusterSpec.rest_password
    }
}

exports.api = (function(){
    return {
        resolve: function(scope, func, args, net){
            // runtime arg resolver
            // handles resolving args that reference scope
            //      syntax:
            //          scope:func:arg1:arg2:...:argN
            if(func in FUNCS){
                return FUNCS[func](scope, args, net)
            } else {
                console.log("Warning: attempted to use unknown spec method ["+func+"]")
            }
        }
    }
})()
