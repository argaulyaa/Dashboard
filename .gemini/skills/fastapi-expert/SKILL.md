---
name: fastapi-expert
description: Best practices for developing, testing, and optimizing FastAPI backend services with WebSockets and Pydantic.
---

# FastAPI Expert Skill

Use this skill when designing, refactoring, or optimizing FastAPI applications for 5G/O-RAN dashboards or high-concurrency microservices.

## Key Guidelines

1. **Async Endpoints**:
   - Use `async def` for I/O bound endpoints (database calls, async HTTP requests, WebSocket streaming).
   - Use standard `def` for synchronous CPU-bound or blocking operations so FastAPI runs them in a thread pool.

2. **WebSocket Robustness**:
   - Handle `WebSocketDisconnect` gracefully in a `try...except` block.
   - Always include heartbeat/ping-pong or periodic state checks to avoid hanging sockets.

3. **Pydantic Validation**:
   - Define strict input/output models using Pydantic.
   - Use field validation and custom error handlers for clear API responses.

4. **Security & CORS**:
   - Restrict `allow_origins` in production CORS middleware.
   - Use Bearer token dependencies (`Depends(require_user)`) for protected routes.
