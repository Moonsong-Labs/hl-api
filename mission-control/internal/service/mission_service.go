package service

import (
	"context"

	"github.com/mission-control/mission-control/internal/domain"
)

// MissionRepository defines persistence operations for missions.
type MissionRepository interface {
	Create(context.Context, domain.Mission) error
	GetByID(context.Context, string) (domain.Mission, error)
}

type MissionService struct {
	repo MissionRepository
}

func NewMissionService(repo MissionRepository) *MissionService {
	return &MissionService{repo: repo}
}

func (s *MissionService) CreateMission(ctx context.Context, mission domain.Mission) error {
	return s.repo.Create(ctx, mission)
}
