# Changelog

All notable changes to Holly Grace will be documented in this file.

This project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-02-09

### Added
- Project renamed from "ecom-agents" / "Forge Scope" to **Holly Grace**
- Multi-model chat UI integrated into main repo (`chat-ui/`)
  - 4 providers: OpenAI, Anthropic, Google, xAI (Grok)
  - 3 modes: Chat, Code (Claude + tools), Socratic (multi-model roundtable)
  - Parameter controls with constraint-aware greying (unsupported params)
  - Server-side param stripping for reasoning models (o1/o3)
- 51 integration tests for chat frontend (42 pass, 9 skip)
- VERSION file and CHANGELOG for semantic versioning
- Comprehensive .gitignore updates

### Changed
- All internal references updated: Forge Scope, ecom-agents, forge-console -> Holly Grace
- Docker containers renamed: holly-postgres, holly-redis, holly-chromadb, holly-ollama
- Docker network renamed: holly-grace
- AWS Terraform variables renamed to holly-grace namespace
- Frontend page title, header, sidebar updated to Holly Grace / HG
- Backend FastAPI titles updated
- pyproject.toml: name = "holly-grace", version = "1.0.0"
- package.json: name = "holly-grace-frontend"

### Architecture
- 4 LLMs: Ollama qwen2.5:3b (orchestrator), GPT-4o (sales), GPT-4o-mini (ops), Opus 4.6 (revenue)
- 818+ tests (148 security + 670 feature + 51 chat frontend)
- 22 implementation phases complete
- Revenue-aware epsilon with 4 financial phases
- Plugin system, webhook RBAC, customer sessions, browser automation
- Multi-channel notifications (Slack, Email)
- Document processing pipeline (PDF, image, CSV)
