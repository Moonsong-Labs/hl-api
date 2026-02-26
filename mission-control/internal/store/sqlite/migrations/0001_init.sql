-- +goose Up
CREATE TABLE IF NOT EXISTS missions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (mission_id) REFERENCES missions(id)
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL,
  task_id TEXT,
  type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (mission_id) REFERENCES missions(id),
  FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_mission_id ON tasks(mission_id);
CREATE INDEX IF NOT EXISTS idx_events_mission_id ON events(mission_id);

-- +goose Down
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS missions;
