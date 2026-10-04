-- Offline only, after backup: deliberately removes Intellectual Life data,
-- preserving all runtime V0.1/V0.2 tables. Never run automatically.
DROP TABLE edge_members;
DROP TABLE edges;
DROP TABLE activity;
DROP TABLE preferences;
DROP TABLE recommendations;
DROP TABLE library_roots;
DROP TABLE knowledge_settings;
DROP TABLE nodes;
PRAGMA user_version=1;
