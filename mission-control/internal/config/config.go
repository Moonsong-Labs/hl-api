package config

import "os"

// Config contains runtime options loaded from environment.
type Config struct {
	HTTPAddr string
	DBPath   string
	AppEnv   string
}

func Load() Config {
	return Config{
		HTTPAddr: getEnv("MC_HTTP_ADDR", ":8080"),
		DBPath:   getEnv("MC_DB_PATH", "./mission_control.db"),
		AppEnv:   getEnv("MC_ENV", "development"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
