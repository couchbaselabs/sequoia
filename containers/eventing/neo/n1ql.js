function OnUpdate(doc, meta) {
    try{
        if(meta.keyspace.scope_name == "scope_0"){
            if(meta.keyspace.collection_name == "coll0"){
                UPSERT INTO n1ql_op.scope_0.coll0 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll1"){
                UPSERT INTO n1ql_op.scope_0.coll1 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll2"){
                UPSERT INTO n1ql_op.scope_0.coll2 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll3"){
                UPSERT INTO n1ql_op.scope_0.coll3 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll4"){
                UPSERT INTO n1ql_op.scope_0.coll4 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else{
                UPSERT INTO $namespace ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
        }
        else{
            if(meta.keyspace.collection_name == "coll0"){
                UPSERT INTO n1ql_op.scope_1.coll0 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll1"){
                UPSERT INTO n1ql_op.scope_1.coll1 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll2"){
                UPSERT INTO n1ql_op.scope_1.coll2 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll3"){
                UPSERT INTO n1ql_op.scope_1.coll3 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else if(meta.keyspace.collection_name == "coll4"){
                UPSERT INTO n1ql_op.scope_1.coll4 ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
            else{
                UPSERT INTO $namespace ( KEY, VALUE ) VALUES ( $$meta.id ,"n1ql insert");
            }
        }
    }
    catch(e){
        log("Query failed: ",e)
    }
}

function OnDelete(meta, options) {
    try{
        if(meta.keyspace.scope_name == "scope_0"){
            if(meta.keyspace.collection_name == "coll0"){
                DELETE FROM n1ql_op.scope_0.coll0 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll1"){
                DELETE FROM n1ql_op.scope_0.coll1 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll2"){
                DELETE FROM n1ql_op.scope_0.coll2 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll3"){
                DELETE FROM n1ql_op.scope_0.coll3 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll4"){
                DELETE FROM n1ql_op.scope_0.coll4 USE KEYS $$meta.id;
            }
            else{
                DELETE from $namespace USE KEYS $$meta.id;
            }
        }
        else{
            if(meta.keyspace.collection_name == "coll0"){
                DELETE FROM n1ql_op.scope_1.coll0 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll1"){
                DELETE FROM n1ql_op.scope_1.coll1 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll2"){
                DELETE FROM n1ql_op.scope_1.coll2 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll3"){
                DELETE FROM n1ql_op.scope_1.coll3 USE KEYS $$meta.id;
            }
            else if(meta.keyspace.collection_name == "coll4"){
                DELETE FROM n1ql_op.scope_1.coll4 USE KEYS $$meta.id;
            }
            else{
                DELETE from $namespace USE KEYS $$meta.id;
            }
        }
    }
    catch(e){
        log("Query failed: ",e)
    }
}