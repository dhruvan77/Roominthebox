Multi-Agent AI Group Discussion System

An AI-powered multi-agent orchestration platform where multiple specialized AI agents collaborate, debate, challenge ideas, and refine solutions through dynamic group discussions.

The system features a Master AI that generates initial ideas and synthesizes the final response, while an intelligent Manager AI dynamically selects specialist agents based on the discussion's context. Each agent contributes a unique perspective, such as Student, Professor, Scientist, Judge, or Technical Expert.

Key Features

- Dynamic multi-agent collaboration and discussion.
- Intelligent role-based agent selection and routing.
- Shared conversation memory and contextual awareness.
- Master AI for initial analysis and final synthesis.
- Real-time discussion updates using Server-Sent Events (SSE).
- Customizable AI roles and perspectives.
- Session management and persistent conversation logs.

Tech Stack

- Language: Python
- Backend: FastAPI
- AI Integration: Groq API
- HTTP Client: HTTPX
- Validation: Pydantic
- Real-time Communication: Server-Sent Events (SSE)

How It Works

The Master AI initiates the discussion, the Manager AI evaluates the conversation and decides which specialist should contribute next, and the selected agents respond using shared discussion context. This process continues until the Manager concludes the discussion, after which the Master AI synthesizes the contributions into a final response.

Core Idea: Instead of relying on a single AI response, bring multiple AI perspectives together to collaboratively reason, critique, and produce better-informed solutions.
