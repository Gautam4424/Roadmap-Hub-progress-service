# 📈 Progress Service: From Scratch to Advanced Guide

Welcome to the definitive guide for the **Progress Service**. This document explains every line of code, the underlying logic, architectural patterns (HLD), and the terminology required to master this microservice.

---

## 🏗️ 1. High-Level Architecture (HLD) & Flow

The **Progress Service** represents the "memory" of a user's learning path. It tracks exactly which nodes (topics) a user has completed in any given roadmap.

### 🔄 End-to-End System Flow Diagram

```mermaid
graph TD
    A[Frontend: SkillForge] -->|POST /progress/toggle| B[API Gateway]
    B -->|Verify JWT & Inject X-User-ID| C[Progress Service]
    C -->|Commit Update| D[(Progress DB)]
    C -->|Publish Event| E[RabbitMQ: roadmap_events]
    F[Notification Service] -.->|Subscribe| E
    G[Leaderboard Service] -.->|Subscribe| E
```

### 🗝️ Key Design Decisions:
1. **Vertical Isolation**: This service uses its own database (`progress_db`). Even if the master `roadmap_db` goes down, user progress is safe.
2. **Gateway-Injected Identity**: To prevent spoofing, the service **trusts** the `X-User-ID` header, which is strictly managed by our API Gateway.
3. **Event-Driven**: We don't wait for other services to update. We just fire a "progress_updated" event to RabbitMQ and return success to the user immediately.

---

## 🛠️ 2. Terminology & Technology Stack

| Term | What is it? | Why use it here? |
| :--- | :--- | :--- |
| **Aio-Pika** | An async RabbitMQ client. | Allows us to talk to the message broker without blocking the API. |
| **Upsert (ON CONFLICT)** | A SQL command that updates OR inserts. | Prevents us from needing a "check if exists" query, which doubles speed. |
| **UUID (Universally Unique ID)** | A 36-character random string. | Much more secure than simple integers (1, 2, 3) because they cannot be guessed. |
| **Alembic** | Database migration engine. | Tracks the history of our `user_progress` table versions. |

---

## 💻 3. Code Breakdown (Line-by-Line)

### 📂 A. Core Configuration (`app/config.py`)
This file loads our system settings.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # The URL to connect to our private PostgreSQL database
    DATABASE_URL: str 
    # The URL for our RabbitMQ message broker
    RABBITMQ_URL: str = "amqp://admin:localdev@localhost:5672/"
    SERVICE_NAME: str = "progress-service"

    # Tells Python to read from a file named ".env"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```
- **`BaseSettings`**: Automatically performs type checking. If `DATABASE_URL` isn't a string, the app won't start.

---

### 🗄️ B. Database Models (`app/models/models.py`)
This defines our "UserProgress" table schema.

```python
class UserProgress(Base):
    __tablename__ = "user_progress"
    
    # 1. Primary Key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 2. User & Content Identifiers
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    roadmap_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    
    # 3. Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # CRITICAL: Ensures a user can only have ONE entry per node
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_user_node_progress"),
    )
```
- **`UniqueConstraint`**: This is our "Safety Net". It stops the same user from completing the same topic twice and cluttering the DB.

---

### 🛣️ C. The Router Logic (`app/routers/progress.py`)
This is the heart of the service. Let's look at the **Toggle** logic:

```python
@router.post("/toggle")
async def toggle(body: ToggleRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # 1. Get the user ID from the header (injected by Gateway)
    user_id = request.headers.get("X-User-ID")
    
    # 2. Prepare the UPSERT statement
    stmt = insert(UserProgress).values(
        user_id=uuid.UUID(user_id), 
        node_id=body.node_id,
        roadmap_id=body.roadmap_id, 
        is_completed=body.completed
    ).on_conflict_do_update(
        index_elements=["user_id", "node_id"], # Where is the conflict?
        set_={"is_completed": body.completed}  # What should we change?
    )
    
    # 3. Save to DB
    await db.execute(stmt)
    await db.commit() # WITHOUT THIS, NOTHING IS SAVED!
    
    # 4. Notify other services via RabbitMQ
    asyncio.create_task(publish_progress_updated(...))
    
    return {"ok": True}
```
- **`on_conflict_do_update`**: This is a PostgreSQL superpower. It handles "Check-then-Create" and "Check-then-Update" in **one single trip** to the database.

---

### 📢 D. Event Broadcasting (`app/events.py`)
How we tell the world about progress:

```python
async def publish_progress_updated(user_id, node_id, roadmap_id, completed):
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        # Declare a TOPIC exchange (allows filtering by other services)
        exchange = await channel.declare_exchange("roadmap_events", "topic", durable=True)
        
        # Publish with a specific routing key
        await exchange.publish(message, routing_key="user.progress.updated")
```
- **`connection`**: Uses `connect_robust` which automatically reconnects if the network blips.

---

## 🛠️ 4. Debugging & Error Log (Experience Shared)

1. **The "Empty DB" Error**: We learned that in Async SQLAlchemy, `execute()` is only half the battle. You **MUST** call `await db.commit()` or the transaction will disappear when the request ends.
2. **The "Duplicate Key" Panic**: Initially, we didn't have `UniqueConstraint`. This caused users to have multiple rows for one topic. Adding the constraint + `ON CONFLICT` fix this forever.
3. **Alembic Paths**: On Windows, PowerShell needs `$env:PYTHONPATH="."` or it won't find your `app` folder during migrations.

---

**Built for the future of RoadmapHub.** 🚀
