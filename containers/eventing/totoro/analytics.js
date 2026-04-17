function OnUpdate(doc, meta) {
    try {
        var rows = [];
        var analyticsIt = couchbase.analyticsQuery(
            "SELECT META(a).id, * FROM `$analytics_dataset_name` a LIMIT 5;"
        );
        for (let row of analyticsIt) {
            rows.push(row);
        }
        dst_bucket[meta.id] = {
            doc_id: meta.id,
            analytics_rows: rows.length,
            data: rows,
            processed_at: new Date().toISOString()
        };
    } catch (e) {
        log("Error in analytics query: ", e);
    }
}

function OnDelete(meta) {
    try {
        delete dst_bucket[meta.id];
    } catch (e) {
        log("Error on delete: ", e);
    }
}
