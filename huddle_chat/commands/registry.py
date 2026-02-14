from typing import TYPE_CHECKING, Any

from huddle_chat.constants import THEMES

if TYPE_CHECKING:
    from chat import ChatApp


class CommandRegistry:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def build(self) -> dict[str, Any]:
        return {
            "/theme": self.command_theme,
            "/setpath": self.command_setpath,
            "/status": self.command_status,
            "/join": self.command_join,
            "/rooms": self.command_rooms,
            "/room": self.command_room,
            "/aiproviders": self.command_aiproviders,
            "/aiconfig": self.command_aiconfig,
            "/ai": self.command_ai,
            "/ask": self.command_ask,
            "/share": self.command_share,
            "/agent": self.command_agent,
            "/memory": self.command_memory,
            "/actions": self.command_actions,
            "/action": self.command_action,
            "/approve": self.command_approve,
            "/deny": self.command_deny,
            "/toolpaths": self.command_toolpaths,
            "/search": self.command_search,
            "/next": self.command_next,
            "/prev": self.command_prev,
            "/clearsearch": self.command_clearsearch,
            "/help": self.command_help,
            "/onboard": self.command_onboard,
            "/exit": self.command_exit,
            "/quit": self.command_exit,
            "/clear": self.command_clear,
            "/me": self.command_me,
        }

    def command_theme(self, args: str) -> None:
        if not args:
            avail = ", ".join(THEMES.keys())
            self.app.append_system_message(f"Available themes: {avail}")
            return
        target = args.strip().lower()
        if target in THEMES:
            self.app.current_theme = target
            self.app.save_config()
            self.app.application.style = self.app.get_style()
            self.app.application.invalidate()
            return
        self.app.append_system_message(f"Unknown theme '{target}'.")

    def command_setpath(self, args: str) -> None:
        self.app.base_dir = args.strip()
        self.app.save_config()
        self.app.application.exit(result="restart")

    def command_status(self, args: str) -> None:
        self.app.status = args[:20]
        self.app.force_heartbeat()

    def command_join(self, args: str) -> None:
        if not args.strip():
            self.app.append_system_message("Usage: /join <room>")
            return
        self.app.switch_room(args.strip())

    def command_rooms(self, _args: str) -> None:
        rooms = ", ".join(self.app.list_rooms())
        self.app.append_system_message(f"Rooms: {rooms}")

    def command_room(self, _args: str) -> None:
        self.app.append_system_message(f"Current room: #{self.app.current_room}")

    def command_aiproviders(self, _args: str) -> None:
        self.app.append_system_message(self.app.get_ai_provider_summary())

    def command_aiconfig(self, args: str) -> None:
        self.app.handle_aiconfig_command(args)

    def command_ai(self, args: str) -> None:
        self.app.handle_ai_command(args)

    def command_ask(self, args: str) -> None:
        self.app.handle_ai_command(args)

    def command_share(self, args: str) -> None:
        self.app.handle_share_command(args)

    def command_agent(self, args: str) -> None:
        self.app.handle_agent_command(args)

    def command_memory(self, args: str) -> None:
        self.app.handle_memory_command(args)

    def command_actions(self, args: str) -> None:
        sub = args.strip().lower()
        if sub == "prune":
            removed = self.app.prune_terminal_actions()
            self.app.append_system_message(f"Pruned {removed} terminal action(s).")
            return
        self.app.append_system_message(self.app.get_pending_actions_text())

    def command_action(self, args: str) -> None:
        action_id = args.strip()
        if not action_id:
            self.app.append_system_message("Usage: /action <action-id>")
            return
        self.app.append_system_message(self.app.get_action_details(action_id))

    def command_approve(self, args: str) -> None:
        action_id = args.strip()
        if not action_id:
            self.app.append_system_message("Usage: /approve <action-id>")
            return
        ok, msg = self.app.decide_action(action_id, "approved")
        self.app.append_system_message(msg)
        if ok:
            self.app.refresh_output_from_events()

    def command_deny(self, args: str) -> None:
        action_id = args.strip()
        if not action_id:
            self.app.append_system_message("Usage: /deny <action-id>")
            return
        ok, msg = self.app.decide_action(action_id, "denied")
        self.app.append_system_message(msg)
        if ok:
            self.app.refresh_output_from_events()

    def command_toolpaths(self, args: str) -> None:
        self.app.handle_toolpaths_command(args)

    def command_search(self, args: str) -> None:
        query = args.strip()
        self.app.search_query = query
        self.app.rebuild_search_hits()
        if not query:
            self.app.append_system_message("Search cleared.")
        elif self.app.search_hits:
            self.app.append_system_message(
                f"Found {len(self.app.search_hits)} matches for '{query}'."
            )
            self.app.jump_to_search_hit(0)
        else:
            self.app.append_system_message(f"No matches for '{query}'.")

    def command_next(self, _args: str) -> None:
        if not self.app.jump_to_search_hit(1):
            self.app.append_system_message("No search matches.")

    def command_prev(self, _args: str) -> None:
        if not self.app.jump_to_search_hit(-1):
            self.app.append_system_message("No search matches.")

    def command_clearsearch(self, _args: str) -> None:
        self.app.search_query = ""
        self.app.search_hits = []
        self.app.active_search_hit_idx = -1
        self.app.append_system_message("Search cleared.")

    def command_help(self, args: str) -> None:
        self.app.handle_help_command(args)

    def command_onboard(self, args: str) -> None:
        self.app.handle_onboard_command(args)

    def command_exit(self, _args: str) -> None:
        self.app.application.exit()

    def command_clear(self, _args: str) -> None:
        self.app.messages = []
        self.app.message_events = []
        self.app.output_field.text = ""
        self.app.search_query = ""
        self.app.search_hits = []
        self.app.active_search_hit_idx = -1

    def command_me(self, args: str) -> None:
        event = self.app.build_event("me", args)
        if not self.app.write_to_file(event):
            self.app.append_system_message(
                "Error: Could not send message. Network busy or locked."
            )
