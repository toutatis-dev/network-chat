from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from huddle_chat.controller import ChatController


class CommandRegistry:
    def __init__(self, controller: "ChatController"):
        self.controller = controller

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
            "/playbook": self.command_playbook,
            "/explain": self.command_explain,
            "/exit": self.command_exit,
            "/quit": self.command_exit,
            "/clear": self.command_clear,
            "/me": self.command_me,
        }

    def command_theme(self, args: str) -> None:
        self.controller.handle_theme_command(args)

    def command_setpath(self, args: str) -> None:
        self.controller.handle_setpath_command(args)

    def command_status(self, args: str) -> None:
        self.controller.handle_status_command(args)

    def command_join(self, args: str) -> None:
        if not args.strip():
            self.controller.app.append_system_message("Usage: /join <room>")
            return
        self.controller.switch_room(args.strip())

    def command_rooms(self, _args: str) -> None:
        self.controller.handle_rooms_command()

    def command_room(self, _args: str) -> None:
        self.controller.handle_room_command()

    def command_aiproviders(self, _args: str) -> None:
        self.controller.handle_aiproviders_command()

    def command_aiconfig(self, args: str) -> None:
        self.controller.handle_aiconfig_command(args)

    def command_ai(self, args: str) -> None:
        self.controller.handle_ai_command(args)

    def command_ask(self, args: str) -> None:
        self.controller.handle_ai_command(args)

    def command_share(self, args: str) -> None:
        self.controller.handle_share_command(args)

    def command_agent(self, args: str) -> None:
        self.controller.handle_agent_command(args)

    def command_memory(self, args: str) -> None:
        self.controller.handle_memory_command(args)

    def command_actions(self, args: str) -> None:
        sub = args.strip().lower()
        if sub == "prune":
            removed = self.controller.prune_terminal_actions()
            self.controller.app.append_system_message(
                f"Pruned {removed} terminal action(s)."
            )
            return
        self.controller.app.append_system_message(
            self.controller.get_pending_actions_text()
        )

    def command_action(self, args: str) -> None:
        action_id = args.strip()
        if not action_id:
            self.controller.app.append_system_message("Usage: /action <action-id>")
            return
        self.controller.app.append_system_message(
            self.controller.get_action_details(action_id)
        )

    def command_approve(self, args: str) -> None:
        action_id = args.strip()
        if not action_id:
            self.controller.app.append_system_message("Usage: /approve <action-id>")
            return
        ok, msg = self.controller.decide_action(action_id, "approved")
        self.controller.app.append_system_message(msg)
        if ok:
            self.controller.refresh_output_from_events()

    def command_deny(self, args: str) -> None:
        action_id = args.strip()
        if not action_id:
            self.controller.app.append_system_message("Usage: /deny <action-id>")
            return
        ok, msg = self.controller.decide_action(action_id, "denied")
        self.controller.app.append_system_message(msg)
        if ok:
            self.controller.refresh_output_from_events()

    def command_toolpaths(self, args: str) -> None:
        self.controller.handle_toolpaths_command(args)

    def command_search(self, args: str) -> None:
        query = args.strip()
        self.controller.app.search_query = query
        self.controller.rebuild_search_hits()
        if not query:
            self.controller.app.append_system_message("Search cleared.")
        elif self.controller.app.search_hits:
            self.controller.app.append_system_message(
                f"Found {len(self.controller.app.search_hits)} matches for '{query}'."
            )
            self.controller.jump_to_search_hit(0)
        else:
            self.controller.app.append_system_message(f"No matches for '{query}'.")

    def command_next(self, _args: str) -> None:
        if not self.controller.jump_to_search_hit(1):
            self.controller.app.append_system_message("No search matches.")

    def command_prev(self, _args: str) -> None:
        if not self.controller.jump_to_search_hit(-1):
            self.controller.app.append_system_message("No search matches.")

    def command_clearsearch(self, _args: str) -> None:
        self.controller.app.search_query = ""
        self.controller.app.search_hits = []
        self.controller.app.active_search_hit_idx = -1
        self.controller.app.append_system_message("Search cleared.")

    def command_help(self, args: str) -> None:
        self.controller.handle_help_command(args)

    def command_onboard(self, args: str) -> None:
        self.controller.handle_onboard_command(args)

    def command_playbook(self, args: str) -> None:
        self.controller.handle_playbook_command(args)

    def command_explain(self, args: str) -> None:
        self.controller.handle_explain_command(args)

    def command_exit(self, _args: str) -> None:
        self.controller.app.application.exit()

    def command_clear(self, _args: str) -> None:
        self.controller.handle_clear_command()

    def command_me(self, args: str) -> None:
        self.controller.handle_me_command(args)
