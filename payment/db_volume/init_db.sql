CREATE TABLE IF NOT EXISTS payment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_client INTEGER NOT NULL UNIQUE,  -- id_client cannot be repeated
    balance FLOAT DEFAULT 0.0,        -- Balance to store money
    creation_date DATETIME DEFAULT CURRENT_TIMESTAMP
);