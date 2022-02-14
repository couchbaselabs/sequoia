function random_index_on_bucket(bkt) {
    var iter =  select name,keyspace_id,scope_id from system:all_indexes where `bucket_id` = $bkt and `using`='gsi';
    let indexes = [];
    for (const row of iter) {
        indexes.push(row);
    }
    random_index = indexes[Math.floor(Math.random() * indexes.length)];
    return random_index
}

function run_n1ql_query(bucket_name) {
    // Get a random index from bucket
    var index = random_index_on_bucket(bucket_name);

    // Get index name and keyspace
    var idx_name = index["name"];
    var idx_template = idx_name.split("_")[0];
    var scope_name = index["scope_id"];
    var collection_name = index["keyspace_id"];
    
    full_keyspace = "`" + bucket_name + "`.`" + scope_name + "`.`" + collection_name + "`"
    
    var query = N1QL(query_template(idx_template, full_keyspace), {});
    let iter = query[Symbol.iterator]();
    var result = iter.next();
    query.close();
    
    return result.value
}

function query_template (index, keyspace) {
    var query_template = {
        "idx1": "select meta().id from keyspacenameplaceholder where country is not null and `type` is not null and (any r in reviews satisfies r.ratings.`Check in / front desk` is not null end) limit 100",
        "idx2": "select avg(price) as AvgPrice, min(price) as MinPrice, max(price) as MaxPrice from keyspacenameplaceholder where free_breakfast=True and free_parking=True and price is not null and array_count(public_likes)>5 and `type`='Hotel' group by country limit 100",
        "idx3": "select city,country,count(*) from keyspacenameplaceholder where free_breakfast=True and free_parking=True group by country,city order by country,city limit 100 offset 100",
        "idx4": "WITH city_avg AS (SELECT city, AVG(price) AS avgprice FROM keyspacenameplaceholder WHERE price IS NOT NULL GROUP BY city) SELECT h.name, h.price FROM keyspacenameplaceholder h JOIN city_avg ON h.city = city_avg.city WHERE h.price < city_avg.avgprice AND h.price IS NOT NULL LIMIT 10;",
        "idx5": "SELECT h.name, h.city, r.author FROM keyspacenameplaceholder h UNNEST reviews AS r WHERE r.ratings.Rooms < 2 AND h.avg_rating >= 3 ORDER BY r.author DESC LIMIT 100;",
        "idx6": "SELECT COUNT(*) FILTER (WHERE free_breakfast = TRUE) AS count_free_breakfast, COUNT(*) FILTER (WHERE free_parking = TRUE) AS count_free_parking, COUNT(*) FILTER (WHERE free_breakfast = TRUE AND free_parking = TRUE) AS count_free_parking_and_breakfast FROM keyspacenameplaceholder WHERE city LIKE 'North%' ORDER BY count_free_parking_and_breakfast DESC LIMIT 10",
        "idx7": "SELECT h.name,h.country,h.city,h.price,DENSE_RANK() OVER (window1) AS `rank` FROM keyspacenameplaceholder AS h WHERE h.price IS NOT NULL WINDOW window1 AS ( PARTITION BY h.country ORDER BY h.price NULLS LAST) LIMIT 10;",
        "idx8": "SELECT * FROM keyspacenameplaceholder AS d WHERE ANY r IN d.reviews SATISFIES r.author LIKE 'M%' AND r.ratings.Cleanliness = 3 END AND free_parking = TRUE AND country IS NOT NULL",
        "idx9": "SELECT * FROM keyspacenameplaceholder AS d WHERE ANY r IN d.reviews SATISFIES r.author LIKE 'M%' and r.ratings.Rooms > 3 END AND free_parking = True",
        "idx10": "SELECT * FROM keyspacenameplaceholder AS d WHERE ANY r IN d.reviews SATISFIES ANY n:v IN r.ratings SATISFIES n = 'Overall' AND v = 2 END END",
        "idx11": "SELECT * FROM keyspacenameplaceholder AS d WHERE ANY r IN d.reviews SATISFIES r.ratings.Rooms = 3 and r.ratings.Cleanliness > 1 END AND free_parking = True"
    }
    return query_template[index].replace("keyspacenameplaceholder", keyspace);
}