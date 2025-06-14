# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Rainfall Notify (雨降り通知アプリ) is a Python application that monitors rainfall sensors and sends notifications when rain starts. It integrates with weather forecast services and provides notifications via LINE messaging and voice announcements.

## Essential Commands

### Running the Application
```bash
# Main application
python src/app.py [-c CONFIG] [-n COUNT] [-D]

# Monitor module directly (for testing)
python src/rainfall/monitor.py [-c CONFIG] [-d] [-D]
```

### Development with Rye
```bash
# Install dependencies
rye sync

# Run tests with coverage
rye run pytest

# Linting and formatting
rye run ruff check .
rye run ruff format .
```

## Architecture Overview

The application follows a sensor-monitoring pattern with external service integrations:

1. **Data Flow**: InfluxDB → Monitor → Weather APIs → Notifications (LINE/Voice)
2. **Core Logic** (`src/rainfall/monitor.py`): 
   - Detects rainfall start from sensor data
   - Filters false positives using solar radiation (>600 W/m² = no rain)
   - Fetches 3-hour precipitation forecasts
   - Sends notifications with weather radar images
   - Enforces time-based voice notification restrictions

3. **External Dependencies**: The codebase extensively uses a custom `my_lib` package (from GitHub) that provides utilities for config, logging, sensors, notifications, and weather data.

## Key Development Notes

1. **Configuration**: Uses JSON Schema validation (`config.schema`). Main config in `config.yaml` (see `config.example.yaml` for reference).

2. **Testing**: Tests use extensive mocking for external services. Coverage reports go to `tests/evidence/`.

3. **Code Style**: Ruff configuration in `.ruff.toml` - 110 char lines, double quotes, 4-space indent.

4. **Monitoring Logic**: 
   - Rainfall threshold: 0.1mm to trigger notifications
   - Deduplication window: 30 minutes for continuous rain
   - Voice announcements: Configurable hours (default 7-21)
   - False positive prevention: Solar radiation check for optical sensors