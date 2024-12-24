CREATE TABLE IF NOT EXISTS payment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,  -- user_id cannot be repeated
    balance FLOAT DEFAULT 0.0,        -- Balance to store money
    creation_date DATETIME DEFAULT CURRENT_TIMESTAMP
);