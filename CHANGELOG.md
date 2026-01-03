# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-01-03

### Added
- Initial release
- Browser context pool with smart management
- Reusable contexts with proxy support and custom tags
- Smart context selection based on tags and availability
- Per-context domain rate limiting
- Context health tracking and auto-recreation on errors
- Eviction strategy for pool management
- CDP (Chrome DevTools Protocol) access for custom network interception
- Docker support with socat for external CDP port forwarding
- FastAPI REST API with unified `/scrape` endpoint
