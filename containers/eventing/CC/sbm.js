function OnUpdate(doc, meta) {
    log("Doc created/updated", meta.id);
    try{
        var meta={"id":meta.id+"_sbm"}
        var result1= couchbase.upsert(dst_bucket,meta,doc);
        log(result1);
    }catch(e){
        log("error:",e);
    }
}

function OnDelete(meta, options) {
    log("Doc deleted/expired", meta.id);
    try{
    var doc={"id":meta.id+"_sbm"}
    var result = couchbase.delete(dst_bucket,doc);
    log(result);
    }catch(e){
        log("error:",e);
    }
}
