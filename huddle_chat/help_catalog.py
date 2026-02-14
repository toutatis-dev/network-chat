from typing import TypedDict


class HelpTopic(TypedDict):
    title: str
    summary: str
    commands: list[str]
    examples: list[str]
    common_errors: list[str]
    related_topics: list[str]


HELP_TOPICS: dict[str, HelpTopic] = {
    "overview": {
        "title": "Overview",
        "summary": (
            "Huddle Chat is a room-based terminal chat client with AI workflows, "
            "memory grounding, agent routing, and approval-gated tool actions."
        ),
        "commands": [
            "/help <topic>",
            "/onboard start",
            "/ai <prompt>",
            "/actions",
            "/memory add",
        ],
        "examples": [
            "/help ai",
            "/onboard status",
            "/ai --act investigate flaky test",
        ],
        "common_errors": [
            "Using /share outside #ai-dm.",
            "Running /approve without checking /action <id> details.",
        ],
        "related_topics": ["ai", "actions", "agent", "memory", "tools"],
    },
    "ai": {
        "title": "AI Requests",
        "summary": "Run AI in shared room context or private local #ai-dm, with optional memory and action proposals.",
        "commands": [
            "/ai [flags] <prompt>",
            "/ai status",
            "/ai cancel",
            "/ask ...",
        ],
        "examples": [
            "/ai summarize today",
            "/ai --private --no-memory draft incident summary",
            "/ai --memory-scope repo,team --act propose refactor plan",
        ],
        "common_errors": [
            "Missing provider API key/model in /aiconfig.",
            "Submitting a second /ai request while one is active.",
        ],
        "related_topics": ["aiconfig", "memory", "actions"],
    },
    "aiconfig": {
        "title": "AI Configuration",
        "summary": "Manage provider keys/models, default provider, and streaming controls.",
        "commands": [
            "/aiproviders",
            "/aiconfig",
            "/aiconfig set-key <provider> <api-key>",
            "/aiconfig set-model <provider> <model>",
            "/aiconfig set-provider <provider>",
            "/aiconfig streaming status",
            "/aiconfig streaming on|off",
        ],
        "examples": [
            "/aiconfig set-key openai sk-...",
            "/aiconfig set-model gemini gemini-2.5-flash",
            "/aiconfig streaming provider openai off",
        ],
        "common_errors": [
            "Using unsupported provider names.",
            "Forgetting to configure a model after setting API key.",
        ],
        "related_topics": ["ai", "agent"],
    },
    "memory": {
        "title": "Memory Workflow",
        "summary": "Draft, edit, and persist memory entries for future AI grounding.",
        "commands": [
            "/memory add",
            "/memory confirm",
            "/memory cancel",
            "/memory edit <field> <value>",
            "/memory scope <private|repo|team>",
            "/memory list [limit]",
            "/memory search <query>",
        ],
        "examples": [
            "/memory add",
            "/memory edit summary We always run ./check.sh before commit",
            "/memory scope repo",
        ],
        "common_errors": [
            "Trying to confirm without an active draft.",
            "Using invalid confidence values (must be low/med/high).",
        ],
        "related_topics": ["ai", "agent"],
    },
    "agent": {
        "title": "Agent Profiles",
        "summary": "Inspect and control the active profile's memory scopes and task routing.",
        "commands": [
            "/agent status",
            "/agent list",
            "/agent use <id>",
            "/agent show [id]",
            "/agent memory <private,repo,team>",
            "/agent route <task-class> <provider> <model>",
        ],
        "examples": [
            "/agent list",
            "/agent route code_analysis openai gpt-4o-mini",
            "/agent memory private,repo,team",
        ],
        "common_errors": [
            "Selecting profile IDs that do not exist.",
            "Setting unsupported providers for routes.",
        ],
        "related_topics": ["tools", "ai", "actions"],
    },
    "actions": {
        "title": "Actions and Approvals",
        "summary": "Actions are approval-gated tool executions proposed by AI or queued manually.",
        "commands": [
            "/actions",
            "/actions prune",
            "/action <action-id>",
            "/approve <action-id>",
            "/deny <action-id>",
        ],
        "examples": [
            "/actions",
            "/action ab12cd34",
            "/approve ab12cd34",
        ],
        "common_errors": [
            "Approving without inspecting /action details.",
            "Trying to approve already terminal actions.",
        ],
        "related_topics": ["tools", "agent", "ai"],
    },
    "tools": {
        "title": "Tool Access",
        "summary": "Tool execution is constrained by tool path roots and agent tool policy.",
        "commands": [
            "/toolpaths list",
            "/toolpaths add <absolute-path>",
            "/toolpaths remove <absolute-path>",
            "/agent show",
        ],
        "examples": [
            "/toolpaths add /home/jack/Dev/network-chat",
            "/toolpaths list",
        ],
        "common_errors": [
            "Adding non-absolute tool paths.",
            "Running tools outside allowed roots.",
        ],
        "related_topics": ["actions", "agent"],
    },
    "rooms": {
        "title": "Rooms and Sharing",
        "summary": "Use shared rooms for collaboration and #ai-dm for local/private AI history.",
        "commands": [
            "/join <room>",
            "/rooms",
            "/room",
            "/share <target-room> <id|start-end>",
        ],
        "examples": [
            "/join ai-dm",
            "/share general 1-3",
        ],
        "common_errors": [
            "Trying /share outside #ai-dm.",
            "Sharing into local-only #ai-dm target.",
        ],
        "related_topics": ["ai", "search"],
    },
    "search": {
        "title": "Search",
        "summary": "Search current room message history and navigate matched entries.",
        "commands": [
            "/search <text>",
            "/next",
            "/prev",
            "/clearsearch",
        ],
        "examples": [
            "/search rollback",
            "/next",
            "/clearsearch",
        ],
        "common_errors": ["Running /next or /prev without active matches."],
        "related_topics": ["rooms"],
    },
}
