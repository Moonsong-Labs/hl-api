package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/mission-control/mission-control/internal/app"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	application, err := app.New(ctx)
	if err != nil {
		panic(err)
	}

	if err := application.Run(ctx); err != nil {
		panic(err)
	}
}
