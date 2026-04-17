function OnUpdate(meta) {
    try {
        var matchQuery = couchbase.SearchQuery.matchAll();
        var it = couchbase.searchQuery("$fts_index_name", matchQuery, { size: 10 });
        var ids = [];
        for (let row of it) {
            ids.push(row.id);
        }
        dst_bucket[meta.id] = {
            doc_id: meta.id,
            fts_hits: ids.length,
            ids: ids,
            processed_at: new Date().toISOString()
        };
    } catch (e) {
        log("Error in fts query: ", e);
    }
}

function OnDelete(meta) {
    try {
        delete dst_bucket[meta.id];
    } catch (e) {
        log("Error on delete: ", e);
    }
}
