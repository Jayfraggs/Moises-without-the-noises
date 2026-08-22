# Audio Engine

Overview
- Centralized Web Audio API logic in `AudioEngine.js`. Owns audio node graph, buffer management, and playback routing.

Responsibilities
- Create buffer sources, gain nodes, and connect to master output.
- Provide an API for components to control stems without creating audio nodes themselves.