# Memory Management System

This document describes the memory and checkpoint management system in ayder-cli.

## Overview

The memory management system provides two related functionalities:

1. **Automatic Checkpoint/Restore** - Prevents context window overflow during long agent sessions
2. **Cross-Session Memory Storage** - Persistent storage of user-saved memories across sessions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        memory.py                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MemoryManager                                       │  │
│  │  ├─ create_checkpoint()  → LLM-based checkpoint       │  │
│  │  ├─ restore_from_checkpoint()                        │  │
│  │  ├─ build_checkpoint_prompt()                        │  │
│  │  ├─ build_restore_prompt()                           │  │
│  │  └─ build_quick_restore_message()                    │  │
│  └──────────────────────────────────────────────────────┘  │
│  ├─ save_memory()  → Cross-session storage (memories.jsonl)│
│  └─ load_memory()                                          │
└──────────────────────┬────────────────────────────────────┘
                       │ imports CHECKPOINT_FILE_NAME
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   checkpoint_manager.py                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CheckpointManager                                   │  │
│  │  ├─ save_checkpoint()  → File I/O only               │  │
│  │  ├─ read_checkpoint()                                │  │
│  │  ├─ has_saved_checkpoint()                           │  │
│  │  ├─ clear_checkpoint()                               │  │
│  │  └─ cycle_count (parsed from file header)            │  │
│  └──────────────────────────────────────────────────────┘  │
│  CHECKPOINT_FILE_NAME = "current_memory.md"                  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. CheckpointManager (`checkpoint_manager.py`)

**Responsibility:** Low-level file I/O for checkpoint operations.

**Key Features:**
- Single file storage: `.ayder/memory/current_memory.md`
- Self-contained metadata in file header (cycle count, timestamp)
- No separate metadata file (simplified from previous version)

**File Format:**
```markdown
# Memory Checkpoint (Cycle 3)
Generated: 2024-01-15T10:30:00

---

<checkpoint content>
```

**API:**
```python
class CheckpointManager:
    def __init__(self, project_ctx: ProjectContext)
    def has_saved_checkpoint(self) -> bool
    def read_checkpoint(self) -> Optional[str]
    def save_checkpoint(self, content: str) -> ToolSuccess
    def clear_checkpoint(self) -> ToolSuccess
    @property
    def cycle_count(self) -> int  # Parsed from file header
```

### 2. MemoryManager (`memory.py`)

**Responsibility:** LLM-based checkpoint operations.

**Key Features:**
- Orchestrates LLM calls to create checkpoints
- Builds prompts for checkpoint and restore operations
- Delegates file I/O to `CheckpointManager`

**API:**
```python
class MemoryManager:
    def __init__(self, project_ctx, llm_provider=None, 
                 tool_executor=None, checkpoint_manager=None)
    
    # Checkpoint operations
    def create_checkpoint(self, session, model, num_ctx, 
                         permissions, verbose) -> bool
    def restore_from_checkpoint(self, session) -> None
    
    # Prompt building
    def build_checkpoint_prompt(self, conversation_summary: str) -> str
    def build_restore_prompt(self, checkpoint_content=None) -> str
    def build_quick_restore_message(self) -> str
```

**Checkpoint Creation Flow:**
1. Build conversation summary from last 10 messages
2. Send checkpoint prompt to LLM
3. LLM uses `write_file` tool to save checkpoint
4. Clear conversation (keep system prompt)
5. Add restore message with checkpoint content

### 3. Cross-Session Memory (`memory.py`)

**Responsibility:** Persistent memory storage across sessions.

**Storage:** `.ayder/memory/memories.jsonl` (JSON Lines format)

**API:**
```python
def save_memory(project_ctx, content, category=None, tags=None) -> str
def load_memory(project_ctx, category=None, query=None, limit=10) -> str
```

**Entry Format:**
```json
{
  "id": "uuid",
  "content": "memory content",
  "category": "architecture",
  "tags": ["db", "backend"],
  "timestamp": "2024-01-15T10:30:00"
}
```

## Automatic Checkpoint System

### Trigger

Checkpoints are automatically triggered when the iteration count exceeds `max_iterations` (default: 50).

### Flow

```
User Input → ChatLoop.run()
                ↓
         IterationController.increment()
                ↓
         should_trigger_checkpoint()? (iteration > max_iterations)
                ↓
         Yes → MemoryManager.create_checkpoint()
                ↓
         LLM writes checkpoint → Clear messages → Restore context
                ↓
         Continue from checkpoint
```

### Configuration

Set via CLI:
```bash
ayder --iterations 100  # Increase checkpoint threshold
```

## User Commands

### Available Commands

| Command | Status | Description |
|---------|--------|-------------|
| `/compact` | ✅ Active | Manual checkpoint: summarize → save → clear → restore |
| `/clear` | ❌ Disabled | Use automatic checkpointing or `/compact` |
| `/summary` | ❌ Disabled | Use automatic checkpointing or `/compact` |
| `/load` | ❌ Disabled | Use automatic checkpointing or `/compact` |

### Using `/compact`

The `/compact` command manually triggers the same flow as automatic checkpointing:

1. Summarizes current conversation
2. Saves to checkpoint file
3. Clears conversation history
4. Restores context from checkpoint

This is useful when you want to manually manage context window before the automatic trigger.

## File Locations

```
.ayder/
└── memory/
    ├── current_memory.md      # Checkpoint content
    └── memories.jsonl         # Cross-session memories
```

## Design Principles

### 1. Separation of Concerns

- **CheckpointManager**: File I/O only
- **MemoryManager**: LLM interactions only
- Commands delegate to MemoryManager rather than duplicating logic

### 2. Single File Checkpoint

Previous versions used two files:
- `current_memory.md` - Content
- `memory_meta.json` - Metadata

Current version uses single file with embedded metadata in header.

### 3. Consistent Path

All checkpoint operations use `.ayder/memory/current_memory.md` (unified from previous inconsistency where commands used `.ayder/current_memory.md`).

## Migration Notes

### From Previous Versions

If you have existing checkpoints at `.ayder/current_memory.md`, move them to `.ayder/memory/current_memory.md`.

```bash
mkdir -p .ayder/memory
mv .ayder/current_memory.md .ayder/memory/current_memory.md
```

## Testing

Run memory-related tests:

```bash
pytest tests/test_memory.py tests/test_checkpoint_manager.py tests/test_chat_loop.py -v
```

Key test coverage:
- Checkpoint save/load/clear operations
- Cycle count parsing from file header
- MemoryManager checkpoint creation flow
- Cross-session memory save/load with filters
