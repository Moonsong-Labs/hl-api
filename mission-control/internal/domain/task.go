package domain

import "time"

type TaskStatus string

const (
	TaskStatusPending TaskStatus = "pending"
	TaskStatusRunning TaskStatus = "running"
	TaskStatusDone    TaskStatus = "done"
	TaskStatusFailed  TaskStatus = "failed"
)

type Task struct {
	ID        string
	MissionID string
	Title     string
	Status    TaskStatus
	CreatedAt time.Time
	UpdatedAt time.Time
}
