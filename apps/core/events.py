"""
Event system for LabControl platform.

Provides a decoupled event-driven architecture for cross-app communication.
Inspired by the production Market backend event system.

Events are triggered asynchronously via Celery, allowing:
- Loose coupling between components
- Scalability and resilience
- Easy testing and mocking
- Clear separation of concerns
"""
from typing import Any, Dict, Type
from celery import shared_task
from django.conf import settings


class EventRegistry:
    """
    Registry for all events in the system.

    Events must be registered using the @EventRegistry.register decorator.
    This allows for centralized event management and discovery.
    """

    _events: Dict[str, Type["BaseEvent"]] = {}

    @classmethod
    def register(cls, event_name: str):
        """
        Decorator to register an event class.

        Usage:
            @EventRegistry.register("study.completed")
            class StudyCompletedEvent(BaseEvent):
                pass
        """

        def decorator(event_class):
            cls._events[event_name] = event_class
            return event_class

        return decorator

    @classmethod
    def get_event(cls, event_name: str) -> Type["BaseEvent"]:
        """Get an event class by name."""
        return cls._events.get(event_name)

    @classmethod
    def list_events(cls):
        """List all registered events."""
        return list(cls._events.keys())


class BaseEvent:
    """
    Base class for all events in the system.

    Events represent significant occurrences in the system that other
    components may want to react to.

    Example:
        @EventRegistry.register("study.completed")
        class StudyCompletedEvent(BaseEvent):
            def __init__(self, study_id, patient_id):
                self.study_id = study_id
                self.patient_id = patient_id

            @classmethod
            def handle(cls, payload):
                # Send notification to patient
                # Update dashboard
                # Log to analytics
                pass

        # Trigger the event
        StudyCompletedEvent(study_id=123, patient_id=456).trigger()
    """

    def __init__(self, **kwargs):
        """
        Initialize the event with data.

        All event-specific data should be passed as kwargs and stored
        in self.data for serialization.
        """
        self.data = kwargs

    def trigger(self):
        """
        Trigger the event asynchronously via Celery.

        The event data is serialized and passed to the Celery task,
        which will call the handle() method in the background.
        """
        event_name = self._get_event_name()
        self.handle_async.delay(event_name, self.data)

    def trigger_sync(self):
        """
        Trigger the event synchronously (for testing).

        This calls handle() directly without going through Celery.
        Useful in tests where CELERY_TASK_ALWAYS_EAGER is not set.
        """
        self.handle(self.data)

    @classmethod
    def _get_event_name(cls):
        """Get the registered name of this event."""
        for name, event_class in EventRegistry._events.items():
            if event_class == cls:
                return name
        return cls.__name__

    @classmethod
    @shared_task(bind=True, name="core.events.handle_event")
    def handle_async(cls, self, event_name: str, payload: Dict[str, Any]):
        """
        Celery task to handle the event asynchronously.

        This is called by trigger() and executes in a Celery worker.

        Args:
            event_name: Name of the event to handle
            payload: Event data dictionary
        """
        event_class = EventRegistry.get_event(event_name)
        if event_class:
            event_class.handle(payload)
        else:
            raise ValueError(f"Event '{event_name}' not found in registry")

    @classmethod
    def handle(cls, payload: Dict[str, Any]):
        """
        Handle the event logic.

        Override this method in subclasses to implement event-specific behavior.

        Args:
            payload: Event data dictionary
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement handle() method"
        )

    @classmethod
    def trigger_batch(cls, events: list):
        """
        Trigger multiple events efficiently in batch.

        This is useful for bulk operations to avoid overwhelming Celery
        with individual tasks.

        Args:
            events: List of event instances to trigger
        """
        # Group events by type for efficient processing
        event_groups = {}
        for event in events:
            event_name = event._get_event_name()
            if event_name not in event_groups:
                event_groups[event_name] = []
            event_groups[event_name].append(event.data)

        # Trigger batch tasks
        for event_name, payloads in event_groups.items():
            cls.handle_batch_async.delay(event_name, payloads)

    @classmethod
    @shared_task(bind=True, name="core.events.handle_batch_event")
    def handle_batch_async(cls, self, event_name: str, payloads: list):
        """
        Celery task to handle multiple events in batch.

        Args:
            event_name: Name of the event type
            payloads: List of event data dictionaries
        """
        event_class = EventRegistry.get_event(event_name)
        if event_class:
            for payload in payloads:
                event_class.handle(payload)
        else:
            raise ValueError(f"Event '{event_name}' not found in registry")
