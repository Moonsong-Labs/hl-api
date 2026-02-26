package domain

import "time"

type Event struct {
	ID        string
	MissionID string
	TaskID    string
	Type      string
	Payload   string
	CreatedAt time.Time
}
