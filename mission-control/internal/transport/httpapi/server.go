package httpapi

import (
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

func NewServer() *http.Server {
	r := chi.NewRouter()
	r.Get("/healthz", healthz)
	r.Get("/readyz", readyz)

	return &http.Server{
		Addr:              ":8080",
		Handler:           r,
		ReadHeaderTimeout: 5 * time.Second,
	}
}

func healthz(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func readyz(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ready"}`))
}
