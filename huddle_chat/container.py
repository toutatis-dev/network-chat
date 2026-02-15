from __future__ import annotations

from dependency_injector import containers, providers  # type: ignore[import-not-found]

from huddle_chat.controller import ChatController
from huddle_chat.event_bus import EventBus
from huddle_chat.providers import GeminiClient, OpenAIClient
from huddle_chat.repositories import (
    ActionRepository,
    AgentRepository,
    ConfigRepository,
    MemoryRepository,
    MessageRepository,
    PresenceRepository,
)
from huddle_chat.services import (
    ActionService,
    AIService,
    AgentService,
    CommandOpsService,
    ExplainService,
    HelpService,
    MemoryService,
    PlaybookService,
    RoutingService,
    RuntimeService,
    StorageService,
    ToolService,
)
from huddle_chat.view import PromptToolkitView


class ChatAppContainer(containers.DeclarativeContainer):
    app = providers.Dependency()

    config_repository = providers.Singleton(ConfigRepository)
    message_repository = providers.Singleton(MessageRepository, app=app)
    presence_repository = providers.Singleton(PresenceRepository, app=app)
    memory_repository = providers.Singleton(MemoryRepository, app=app)
    agent_repository = providers.Singleton(AgentRepository, app=app)
    action_repository = providers.Singleton(ActionRepository)

    storage_service = providers.Singleton(StorageService, app=app)
    memory_service = providers.Singleton(MemoryService, app=app)
    ai_service = providers.Singleton(AIService, app=app)
    agent_service = providers.Singleton(AgentService, app=app)
    routing_service = providers.Singleton(RoutingService, app=app)
    action_service = providers.Singleton(ActionService, app=app)
    tool_service = providers.Singleton(ToolService, app=app)
    command_ops_service = providers.Singleton(CommandOpsService, app=app)
    help_service = providers.Singleton(HelpService, app=app)
    playbook_service = providers.Singleton(PlaybookService, app=app)
    explain_service = providers.Singleton(ExplainService, app=app)
    runtime_service = providers.Singleton(RuntimeService, app=app)

    event_bus = providers.Singleton(EventBus, maxsize=512, publish_timeout_seconds=0.1)
    controller = providers.Singleton(ChatController, app=app)
    view = providers.Singleton(
        PromptToolkitView,
        app=app,
        on_submit=providers.Callable(
            lambda controller: controller.handle_input, controller
        ),
    )

    ai_provider_clients = providers.Callable(
        lambda gemini, openai: {"gemini": gemini, "openai": openai},
        gemini=providers.Factory(GeminiClient),
        openai=providers.Factory(OpenAIClient),
    )
