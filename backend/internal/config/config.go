package config

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Config struct {
	Port        int
	DatabaseURL string
}

func Load() (Config, error) {
	envPath := filepath.Join(".", ".env")
	values, err := loadDotEnvFile(envPath)
	if err != nil {
		return Config{}, err
	}

	cfg := Config{Port: 8080}
	if portRaw := strings.TrimSpace(values["PORT"]); portRaw != "" {
		port, err := strconv.Atoi(portRaw)
		if err != nil || port <= 0 {
			return Config{}, fmt.Errorf("invalid PORT: %q", portRaw)
		}
		cfg.Port = port
	}

	cfg.DatabaseURL = strings.TrimSpace(values["DATABASE_URL"])
	if cfg.DatabaseURL == "" {
		return Config{}, fmt.Errorf("DATABASE_URL is required")
	}

	return cfg, nil
}

func loadDotEnvFile(path string) (map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("%s not found; create it from .env.example", path)
		}
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	defer file.Close()

	values := map[string]string{}
	scanner := bufio.NewScanner(file)
	for lineNo := 1; scanner.Scan(); lineNo++ {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		keyValue := strings.SplitN(line, "=", 2)
		if len(keyValue) != 2 {
			return nil, fmt.Errorf("invalid .env line %d: %q", lineNo, line)
		}

		key := strings.TrimSpace(keyValue[0])
		value := strings.TrimSpace(keyValue[1])
		if key == "" {
			return nil, fmt.Errorf("invalid .env line %d: empty key", lineNo)
		}

		if strings.HasPrefix(key, "export ") {
			key = strings.TrimSpace(strings.TrimPrefix(key, "export "))
		}

		if len(value) >= 2 {
			if (value[0] == '\'' && value[len(value)-1] == '\'') ||
				(value[0] == '"' && value[len(value)-1] == '"') {
				value = value[1 : len(value)-1]
			}
		}

		values[key] = value
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}

	return values, nil
}
