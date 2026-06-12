DROP TABLE IF EXISTS lookup_cache;

CREATE TABLE lookup_cache (
    number TEXT PRIMARY KEY,
    name TEXT,
    carrier TEXT,
    line_type TEXT,
    source TEXT,
    updated_at TEXT
);
