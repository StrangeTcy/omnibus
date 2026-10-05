CREATE TABLE collection_jobs(id TEXT PRIMARY KEY, created TEXT NOT NULL, data TEXT NOT NULL CHECK(json_valid(data)));
PRAGMA user_version=3;
