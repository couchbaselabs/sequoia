
# Synonym Search Testing

Synonyms are words that share equivalent meanings and can be considered interchangeable. In information retrieval systems, enabling synonym search ensures that when a word is searched, all of its synonyms are also searched, resulting in a more comprehensive and relevant result set. This enhancement improves the overall quality and accuracy of the search results.

Here, the goal is to test this feature without third party dependencies (eg. elastic).


<br>


## Methodology

The data is generated from this thesaurus. Out of all the features the thesaurus contains, we only require the main word and its corresponding synonym list. This preprocessing is done in `pre-process/pre_process.go`


Post preprocessing, we push the synonym data to a specific collection `synonym collection`

The source data generation is mentioned below as a illustration
<br>

![source_loader](https://github.com/user-attachments/assets/3b298b46-7644-44c3-b1db-95d2b3760a8c)


<br>

## API Reference

#### Push Synonym data

```
POST http://localhost:5000/run/syn-loader
```

| Parameter | Type     | Description                |
| :-------- | :------- | :------------------------- |
| `bucket` | `string` | **Required**. Bucket name |
| `scope` | `string` | **Required**. Scope name |
| `collection` | `string` | **Required**. Collection name |
| `workers` | `int` | **Required**. Number of workers |
| `couchbase` | `string` | **Required**. Host name |
| `user` | `string` | **Required**. Couchbase username |
| `pass` | `string` | **Required**. Couchbase password |
| `format` | `int` | **Required**. Format of the synonym document|

<br>

#### Push Source data and return the groundtruth

```
POST http://localhost:5000/run/src-loader
```

| Parameter | Type     | Description                |
| :-------- | :------- | :------------------------- |
| `bucket` | `string` | **Required**. Bucket name |
| `scope` | `string` | **Required**. Scope name |
| `collection` | `string` | **Required**. Collection name |
| `workers` | `int` | **Required**. Number of workers |
| `couchbase` | `string` | **Required**. Host name |
| `user` | `string` | **Required**. Couchbase username |
| `pass` | `string` | **Required**. Couchbase password |
| `numDocs` | `int` | **Required**. Number of docs to generate |


