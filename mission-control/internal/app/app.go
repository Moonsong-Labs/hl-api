package app

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/mission-control/mission-control/internal/config"
	"github.com/mission-control/mission-control/internal/store/sqlite"
	"github.com/mission-control/mission-control/internal/transport/httpapi"
	"github.com/mission-control/mission-control/pkg/observability"
	"go.uber.org/zap"
)

type App struct {
	cfg    config.Config
	logger *zap.Logger
	store  *sqlite.Store
	http   *http.Server
}

func New(ctx context.Context) (*App, error) {
	_ = ctx
	cfg := config.Load()

	logger, err := observability.NewLogger(cfg.AppEnv)
	if err != nil {
		return nil, fmt.Errorf("create logger: %w", err)
	}

	store, err := sqlite.New(cfg.DBPath)
	if err != nil {
		return nil, fmt.Errorf("create sqlite store: %w", err)
	}

	if err := store.Migrate(context.Background()); err != nil {
		return nil, fmt.Errorf("migrate sqlite: %w", err)
	}

	srv := httpapi.NewServer()
	srv.Addr = cfg.HTTPAddr

	return &App{cfg: cfg, logger: logger, store: store, http: srv}, nil
}

func (a *App) Run(ctx context.Context) error {
	a.logger.Info("starting mission-control", zap.String("addr", a.cfg.HTTPAddr), zap.String("db", a.cfg.DBPath))

	errCh := make(chan error, 1)
	go func() {
		if err := a.http.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()

	select {
	case <-ctx.Done():
		a.logger.Info("shutdown signal received")
	case err := <-errCh:
		return fmt.Errorf("http server failed: %w", err)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := a.http.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("shutdown http server: %w", err)
	}

	if err := a.store.Close(); err != nil {
		return fmt.Errorf("close sqlite store: %w", err)
	}

	_ = a.logger.Sync()
	return nil
}
