function OnUpdate(doc, meta) {
    try{
        var query = UPSERT INTO $namespace ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
    }
    catch(e){
        log("Query failed: ",e)
    }
}

function OnDelete(meta, options) {
try{
        var query = DELETE from $namespace USE KEYS $$meta.id ;
    }
    catch(e){
        log("Query failed: ",e)
    }
}