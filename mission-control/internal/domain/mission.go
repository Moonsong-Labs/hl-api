package domain

import "time"

type MissionStatus string

const (
	MissionStatusPlanned   MissionStatus = "planned"
	MissionStatusActive    MissionStatus = "active"
	MissionStatusCompleted MissionStatus = "completed"
	MissionStatusAborted   MissionStatus = "aborted"
)

type Mission struct {
	ID          string
	Name        string
	Description string
	Status      MissionStatus
	CreatedAt   time.Time
	UpdatedAt   time.Time
}
