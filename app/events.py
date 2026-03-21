import json
import uuid
import aio_pika
import structlog
from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

async def publish_progress_updated(user_id: str, node_id: str, roadmap_id: str, completed: bool):
    """Publish progress update event to RabbitMQ for other services (e.g., Notification)."""
    try:
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange("roadmap_events", aio_pika.ExchangeType.TOPIC, durable=True)
            
            message_body = {
                "event": "progress_updated",
                "user_id": user_id,
                "node_id": node_id,
                "roadmap_id": roadmap_id,
                "completed": completed,
                "timestamp": str(uuid.uuid4()) # Just to make it unique if needed
            }
            
            message = aio_pika.Message(
                body=json.dumps(message_body).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            await exchange.publish(message, routing_key="user.progress.updated")
            logger.info("Published progress_updated event", user_id=user_id, node_id=node_id)
    except Exception as e:
        logger.error("Failed to publish progress_updated event", error=str(e))
