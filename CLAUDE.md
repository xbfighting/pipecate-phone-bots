# Project Development Guidelines

## Core Development Principles

### Quality First Approach
- We prioritize HIGH QUALITY code and exceptional UI/UX over speed
- Take time to ensure code quality and maintainability
- Follow the principle of small steps and fast progress

### Workflow Requirements

#### 1. Discussion Before Implementation
**IMPORTANT**: ALWAYS discuss and confirm the solution approach BEFORE writing any code
- Present a clear plan outlining the proposed implementation
- Wait for user confirmation before proceeding
- Use TodoWrite tool to track implementation steps

#### 2. Feature Development Standards
For **features**:
- Design with scalability and extensibility in mind
- Follow existing architectural patterns
- Include comprehensive error handling
- Consider edge cases and failure scenarios

For **bugfixes**:
- Identify root cause, not just symptoms
- Include regression prevention measures
- Document the fix approach in commit messages

#### 3. Milestone Management
- Split work into small, manageable milestones using TodoWrite
- Generate a summary for review before completing each milestone
- Get confirmation before moving to the next milestone

#### 4. Code Quality Standards
- Follow existing code conventions and patterns
- Ensure proper typing (avoid `any` types in TypeScript)
- Include meaningful variable and function names
- Keep functions focused and single-purpose

#### 5. Testing Requirements
- Write unit tests for new features
- Ensure existing tests pass before marking tasks complete
- Run linting and type checking before completion

## Project-Specific Context

### Technology Stack
[TODO: Add your technology stack here]
- Language: 
- Framework: 
- Testing: 
- Build tools: 

### Architecture Patterns
[TODO: Document your architecture patterns]

### Common Commands
[TODO: Add your project commands]
- Build: 
- Test: 
- Lint: 
- Type Check: 

### Using Custom Agents
You can invoke specialized agents for specific tasks:
- `@feature-planner` - For planning new features
- `@code-reviewer` - For reviewing code changes
- `@test-writer` - For writing unit tests

Example: "Use @feature-planner to design a user authentication system"

## Communication Style
- Be concise but thorough in technical discussions
- Always explain the "why" behind implementation decisions
- Proactively identify potential issues or improvements

## Remember
1. **NEVER** proceed with implementation without discussing the approach first
2. **ALWAYS** use TodoWrite to track progress
3. **ALWAYS** run quality checks before completing tasks
4. **PRIORITIZE** code quality over delivery speed