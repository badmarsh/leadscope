# Behavioral Rules

- **Testing & Validation**: After each implementation of new features OR bug fixes, you must systematically rebuild and test them to ensure functionality and prevent regressions.
- **Docker Infrastructure**: Whenever you modify Docker infrastructure files (e.g., `docker-compose.yml`, `Dockerfile`, or environment variables), you MUST explicitly run `docker compose up -d --build` to apply the changes and restart the containers. Do not assume changes take effect automatically.
