from __future__ import annotations

from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import (
    Float,
    FloatContainer,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.widgets import Frame, TextArea

from huddle_chat.ui import ChatLexer, SlashCompleter

if TYPE_CHECKING:
    from chat import ChatApp


class PromptToolkitView:
    def __init__(self, app: "ChatApp", on_submit: Callable[[str], None]):
        self.app = app
        self.on_submit = on_submit

        self.output_field = TextArea(
            style="class:chat-area",
            focusable=False,
            wrap_lines=True,
            lexer=ChatLexer(app),
        )
        self.input_field = TextArea(
            height=3,
            prompt="> ",
            style="class:input-area",
            multiline=False,
            wrap_lines=False,
            completer=SlashCompleter(app),
            complete_while_typing=True,
        )
        self.sidebar_control = FormattedTextControl()
        self.sidebar_window = Window(
            content=self.sidebar_control, width=34, style="class:sidebar"
        )

        self.key_bindings = KeyBindings()

        @self.key_bindings.add("enter")
        def _submit(_event: Any) -> None:
            self.on_submit(self.input_field.text)

        @self.key_bindings.add("tab")
        def _complete(event: Any) -> None:
            buffer = event.current_buffer
            complete_state = buffer.complete_state
            if complete_state is not None:
                completion = complete_state.current_completion
                if completion is None and complete_state.completions:
                    completion = complete_state.completions[0]
                if completion is not None:
                    buffer.apply_completion(completion)
                    return
            buffer.start_completion(select_first=True)

        @self.key_bindings.add("c-c")
        def _exit(event: Any) -> None:
            event.app.exit()

        root_container = HSplit(
            [
                VSplit(
                    [
                        Frame(self.output_field, title="Chat History"),
                        Frame(self.sidebar_window, title="Online"),
                    ]
                ),
                Frame(self.input_field, title="Your Message (/ for commands)"),
            ]
        )

        self.layout_container = FloatContainer(
            content=root_container,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=16, scroll_offset=1),
                )
            ],
        )
        self.application: Any = Application(
            layout=Layout(self.layout_container),
            key_bindings=self.key_bindings,
            style=app.get_style(),
            full_screen=True,
            mouse_support=True,
        )

    def invalidate(self) -> None:
        self.application.invalidate()

    async def run_async(self) -> Any:
        return await self.application.run_async()

    def exit(self, result: str | None = None) -> None:
        self.application.exit(result=result)
