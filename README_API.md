# dbs-vector API Documentation

This document outlines the API specifications and usage for the `dbs-vector` search engine.

## Overview
The `dbs-vector` API provides a high-performance, asynchronous REST interface for hybrid (Vector + Full-Text) codebase search. It is built using **FastAPI** and runs on a local Uvicorn ASGI server.

To minimize latency and maximize performance, the application leverages Apple's Unified Memory Architecture (UMA). The MLX embedding model and LanceDB connection are initialized *once* for each engine defined in `config.yaml` during the application's startup lifecycle, remaining resident in memory across requests.

## Starting the Server
You can launch the API server using the Typer CLI:

```bash
uv run dbs-vector serve
```

### Options
*   `--host` / `-h`: The host interface to bind to (Default: `127.0.0.1`).
*   `--port` / `-p`: The port to bind to (Default: `8000`).
*   `--reload`: Enable auto-reload for local development.
*   `--config-file` / `-c`: Path to your custom `config.yaml`.

By default, the server will start at `http://127.0.0.1:8000`. 
FastAPI automatically generates interactive Swagger UI documentation, accessible at `http://127.0.0.1:8000/docs`.

---

## Endpoints

### 1. Health Check
Checks the initialization status of the API and the loaded models for all configured engines.

*   **URL:** `/health`
*   **Method:** `GET`

**Success Response (200 OK):**
Returns the status and the model name for every active engine.
```json
{
  "status": "healthy",
  "md_model": "mlx-community/all-MiniLM-L6-v2-4bit",
  "sql_model": "bigcode/starencoder"
}
```

**Error Response (503 Service Unavailable):**
If the search services are still initializing or failed to load.
```json
{
  "detail": "Search service initializing or failed"
}
```

---

### 2. Search Documents (md)
Executes a hybrid search query against the document vector store (`knowledge_vault`).

*   **URL:** `/search/md`
*   **Method:** `POST`
*   **Content-Type:** `application/json`

**Request Body (JSON):**
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `query` | `string` | **Yes** | The semantic text query to search for. |
| `limit` | `integer` | No | Maximum number of results to return (Default: 5). |
| `source_filter` | `string` | No | Optional exact-match path/file to filter the search results. |

---

### 3. Search SQL (sql)
Executes a hybrid search query against the SQL query vector store (`query_vault`).

*   **URL:** `/search/sql`
*   **Method:** `POST`
*   **Content-Type:** `application/json`

**Request Body (JSON):**
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `query` | `string` | **Yes** | The semantic SQL query to search for. |
| `limit` | `integer` | No | Maximum number of results to return (Default: 5). |
| `source_filter` | `string` | No | Optional exact-match database name to filter the search. |
| `min_time` | `float` | No | Optional minimum execution time in milliseconds to filter results. |

---

## Response Structure
Both search endpoints return a similar structure containing the original query and an array of result objects.

**Example Markdown Response:**
```json
{
  "query": "How does Unified Memory mapping work?",
  "results": [
    {
      "chunk": {
        "id": "docs/README.md_chunk_5",
        "text": "Unified Memory mapping (Forces MLX Lazy Evaluation)...",
        "source": "docs/README.md",
        "content_hash": "a1b2c3d4e5f6g7h8",
        "node_type": null,
        "parent_scope": null,
        "line_range": null
      },
      "score": 0.8523,
      "distance": 0.1477,
      "is_fts_match": false
    }
  ]
}
```

**Example SQL Response:**
```json
{
  "query": "SELECT * FROM users",
  "results": [
    {
      "chunk": {
        "id": "query_abc123",
        "text": "SELECT * FROM users WHERE id = ?",
        "raw_query": "SELECT * FROM users WHERE id = 42",
        "source": "production_db",
        "execution_time_ms": 1250.5,
        "calls": 500,
        "content_hash": "hash_xyz789"
      },
      "score": 0.9812,
      "distance": 0.0188,
      "is_fts_match": false
    }
  ]
}
```

---

## Concurrency and Threading
Because the MLX embedder and LanceDB search operations are blocking (synchronous), the API utilizes `asyncio.to_thread`. This allows the asynchronous FastAPI event loop to remain unblocked and responsive to concurrent incoming HTTP requests (like `/health` checks) while the heavy GPU inference is offloaded to a thread pool. A `threading.Lock` is used internally to ensure that the MLX model is accessed safely across threads.
