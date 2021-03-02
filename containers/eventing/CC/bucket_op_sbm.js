function OnUpdate(doc, meta) {
    log("Doc created/updated", meta.id);
    try{
        var result1= couchbase.insert(dst_bucket,meta,doc);
        log(result1);
        var result2= couchbase.insert(dst_bucket2,meta,doc);
        log(result2);
    }catch(e){
        log("error:",e);
    }
}

function OnDelete(meta, options) {
    log("Doc deleted/expired", meta.id);
    try{
    var doc={"id":meta.id}
    var result1 = couchbase.delete(dst_bucket,doc);
    log(result1);
    var result2 = couchbase.delete(dst_bucket2,doc);
    log(result2);
    }catch(e){
       log("error:",e);
    }
}
