import os
import time
import json
import asyncio
import sys
import string
from datetime import datetime
from threading import Thread

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window, VSplit, FloatContainer, Float
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.layout.menus import CompletionsMenu

# Global Configuration
CONFIG_FILE = "chat_config.json"
DEFAULT_PATH = None

# Themes Configuration
THEMES = {
    'default': {
        'chat-area': 'bg:#000000 #ffffff',
        'input-area': 'bg:#222222 #ffffff',
        'sidebar': 'bg:#111111 #88ff88',
        'frame.label': 'bg:#0000aa #ffffff bold',
        'status': 'bg:#004400 #ffffff',
        'completion-menu': 'bg:#333333 #ffffff',
        'completion-menu.completion.current': 'bg:#00aaaa #000000',
    },
    'nord': {
        'chat-area': 'bg:#2E3440 #D8DEE9',      # Polar Night / Snow Storm
        'input-area': 'bg:#3B4252 #ECEFF4',     # Slightly lighter background
        'sidebar': 'bg:#434C5E #8FBCBB',        # Frost / Aurora
        'frame.label': 'bg:#5E81AC #ECEFF4 bold', # Frost Blue
        'status': 'bg:#A3BE8C #2E3440',         # Aurora Green
        'completion-menu': 'bg:#4C566A #ECEFF4',
        'completion-menu.completion.current': 'bg:#88C0D0 #2E3440',
    },
    'matrix': {
        'chat-area': 'bg:#000000 #00FF00',
        'input-area': 'bg:#001100 #00DD00',
        'sidebar': 'bg:#001100 #00FF00',
        'frame.label': 'bg:#003300 #00FF00 bold',
        'status': 'bg:#004400 #ffffff',
        'completion-menu': 'bg:#002200 #00FF00',
        'completion-menu.completion.current': 'bg:#00FF00 #000000',
    },
    'solarized-dark': {
        'chat-area': 'bg:#002b36 #839496',
        'input-area': 'bg:#073642 #93a1a1',
        'sidebar': 'bg:#073642 #2aa198',
        'frame.label': 'bg:#268bd2 #fdf6e3 bold',
        'status': 'bg:#859900 #fdf6e3',
        'completion-menu': 'bg:#073642 #93a1a1',
        'completion-menu.completion.current': 'bg:#2aa198 #002b36',
    },
    'monokai': {
        'chat-area': 'bg:#272822 #F8F8F2',
        'input-area': 'bg:#3E3D32 #F8F8F2',
        'sidebar': 'bg:#272822 #A6E22E',
        'frame.label': 'bg:#F92672 #F8F8F2 bold',
        'status': 'bg:#66D9EF #272822',
        'completion-menu': 'bg:#3E3D32 #F8F8F2',
        'completion-menu.completion.current': 'bg:#FD971F #272822',
    }
}

COLORS = ["green", "cyan", "magenta", "yellow", "blue", "red", "white", "brightgreen", "brightcyan", "brightmagenta", "brightyellow", "brightblue", "brightred"]

class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith('/theme '):
            # Suggest themes
            prefix = text[7:].lower()
            for theme_name in THEMES.keys():
                if theme_name.startswith(prefix):
                    yield Completion(theme_name, start_position=-len(prefix), display=theme_name)
        elif text.startswith('/'):
            commands = [
                ('/status', 'Set your status (e.g. /status Busy)'),
                ('/theme', 'Change color theme (e.g. /theme nord)'),
                ('/me', 'Perform an action (e.g. /me waves)'),
                ('/setpath', 'Change the chat server path'),
                ('/exit', 'Quit the application'),
                ('/clear', 'Clear local chat history'),
            ]
            word = text.lower()
            for cmd, desc in commands:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word), display=cmd, display_meta=desc)

class ChatLexer(Lexer):
    def __init__(self, app_ref):
        self.app_ref = app_ref
        
    def lex_document(self, document):
        def get_line_tokens(line_num):
            try:
                line_text = document.lines[line_num]
                if ": " in line_text:
                    parts = line_text.split(": ", 1)
                    prefix = parts[0]
                    if "] " in prefix:
                        ts_str, name = prefix.split("] ", 1)
                        ts_clean = ts_str.replace("[", "")
                        user_data = self.app_ref.online_users.get(name, {})
                        u_color = user_data.get('color', 'white')
                        return [
                            ('class:timestamp', "[" + ts_clean + "] "),
                            (f'fg:{u_color} bold', name),
                            ('', ": " + parts[1])
                        ]
            except Exception: pass
            return [('', document.lines[line_num])]
        return get_line_tokens

class ChatApp:
    def __init__(self):
        self.name = "Anonymous"
        self.color = "white"
        self.status = ""
        self.running = True
        self.last_pos = 0
        self.messages = []
        self.online_users = {}
        
        # Load Config
        config_data = self.load_config_data()
        self.base_dir = config_data.get('path', DEFAULT_PATH)
        self.current_theme = config_data.get('theme', 'default')
        
        # Validate path if missing (prompt user)
        if not self.base_dir or not os.path.exists(self.base_dir):
            self.base_dir = self.prompt_for_path()
            self.save_config()

        self.chat_file = os.path.join(self.base_dir, "Shared_chat.txt")
        self.presence_dir = os.path.join(self.base_dir, "presence")
        self.ensure_paths()

        # TUI Setup
        self.output_field = TextArea(style='class:chat-area', focusable=False, wrap_lines=True, lexer=ChatLexer(self))
        self.input_field = TextArea(height=3, prompt='> ', style='class:input-area', multiline=False, wrap_lines=False, completer=SlashCompleter(), complete_while_typing=True)
        self.sidebar_control = FormattedTextControl()
        self.sidebar_window = Window(content=self.sidebar_control, width=30, style='class:sidebar')

        self.kb = KeyBindings()
        @self.kb.add('enter')
        def _(event):
            self.handle_input(self.input_field.text)
        @self.kb.add('c-c')
        def _(event):
            event.app.exit()

        root_container = HSplit([
            VSplit([
                Frame(self.output_field, title=f"Chat History"),
                Frame(self.sidebar_window, title="Online"),
            ]),
            Frame(self.input_field, title="Your Message (/ for commands)"),
        ])
        
        self.layout_container = FloatContainer(
            content=root_container,
            floats=[Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=16, scroll_offset=1))]
        )

        self.application = Application(
            layout=Layout(self.layout_container), 
            key_bindings=self.kb, 
            style=self.get_style(), 
            full_screen=True, 
            mouse_support=True
        )

    def load_config_data(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except: pass
        return {}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'path': self.base_dir, 'theme': self.current_theme}, f)

    def get_style(self):
        theme_dict = THEMES.get(self.current_theme, THEMES['default'])
        # Merge basic defaults if needed, but THEMES should be complete enough
        base_dict = {
            'scrollbar.background': 'bg:#222222',
            'scrollbar.button': 'bg:#777777',
        }
        base_dict.update(theme_dict)
        return Style.from_dict(base_dict)

    def get_available_drives(self):
        drives = []
        try:
            if os.name == 'nt':
                bitmask = os.popen('fsutil fsinfo drives').read().strip()
            # This often returns junk text on some systems, fallback loop is safer
        except: pass
        for letter in string.ascii_uppercase:
            if os.path.exists(f"{letter}:\\"):
                drives.append(f"{letter}:\\")
        return drives

    def prompt_for_path(self):
        print("--- Huddle Chat Setup ---")
        print("Available Drives detected:")
        try:
            drives = self.get_available_drives()
            print("  " + ", ".join(drives))
        except: pass

        if DEFAULT_PATH:
            print(f"\nDefault Server: {DEFAULT_PATH}")
            prompt_msg = "Enter server path [Press Enter for default]: "
        else:
            prompt_msg = "Enter server path: "

        while True:
            user_path = input(prompt_msg).strip()
            
            if not user_path:
                if DEFAULT_PATH:
                    base_dir = DEFAULT_PATH
                else:
                    continue
            else:
                base_dir = user_path

            base_dir = base_dir.replace('"', '').replace("'", "")
            
            if os.path.exists(base_dir):
                return base_dir
            else:
                print(f"Warning: Path '{base_dir}' was not found.")
                choice = input("Is this a mapped drive? Force use anyway? (y/n/create): ").lower()
                if choice == 'y': return base_dir
                elif choice == 'create':
                    try:
                        os.makedirs(base_dir)
                        return base_dir
                    except Exception as e:
                        print(f"Failed to create: {e}")

    def ensure_paths(self):
        if not os.path.exists(self.presence_dir):
            try: os.makedirs(self.presence_dir)
            except: pass

    def get_online_users(self):
        online = {}
        now = time.time()
        if not os.path.exists(self.presence_dir): return online
        for filename in os.listdir(self.presence_dir):
            try:
                path = os.path.join(self.presence_dir, filename)
                if now - os.path.getmtime(path) < 30:
                    with open(path, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, dict): online[filename] = data
                        else: online[filename] = {'color': 'white', 'status': ''}
                else:
                    try: os.remove(path)
                    except: pass
            except: pass
        return online

    def heartbeat(self):
        presence_path = os.path.join(self.presence_dir, self.name)
        while self.running:
            try:
                data = {'color': self.color, 'last_seen': time.time(), 'status': self.status}
                with open(presence_path, 'w') as f:
                    json.dump(data, f)
            except: pass
            self.online_users = self.get_online_users()
            self.update_sidebar()
            time.sleep(10)
        if os.path.exists(presence_path):
            try: os.remove(presence_path)
            except: pass

    def update_sidebar(self):
        lines = []
        users = sorted(self.online_users.keys())
        for user in users:
            data = self.online_users[user]
            color = data.get('color', 'white')
            status = data.get('status', '')
            line = f'<style fg="{color}">● {user}</style>'
            if status: line += f' <style fg="#888888">[{status}]</style>'
            lines.append(line)
        self.sidebar_control.text = HTML("\n".join(lines))
        self.application.invalidate()

    def handle_input(self, text):
        text = text.strip()
        if not text: return
        
        if text.startswith('/'):
            parts = text.split(' ', 1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            if command == '/theme':
                if not args:
                    # List themes in chat
                    avail = ", ".join(THEMES.keys())
                    self.output_field.text += f"\n[System] Available themes: {avail}\n"
                    self.output_field.buffer.cursor_position = len(self.output_field.text)
                else:
                    target = args.strip().lower()
                    if target in THEMES:
                        self.current_theme = target
                        self.save_config()
                        self.application.style = self.get_style() # Hot-reload style
                        self.application.invalidate()
                    else:
                        self.output_field.text += f"\n[System] Unknown theme '{target}'.\n"
                        self.output_field.buffer.cursor_position = len(self.output_field.text)
                self.input_field.text = ""
                return

            if command == '/setpath':
                new_path = args.strip()
                self.base_dir = new_path
                self.save_config()
                self.application.exit(result='restart')
                return

            if command == '/status':
                self.status = args[:20]
                Thread(target=self.force_heartbeat).start()
                self.input_field.text = ""
                return
            if command in ['/exit', '/quit']:
                self.application.exit()
                return
            if command == '/clear':
                self.messages = []
                self.output_field.text = ""
                self.input_field.text = ""
                return
            if command == '/me':
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.write_to_file(f"[{timestamp}] * {self.name} {args}\n")
                self.input_field.text = ""
                return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write_to_file(f"[{timestamp}] {self.name}: {text}\n")
        self.input_field.text = ""

    def write_to_file(self, msg):
        lock_file = self.chat_file + ".lock"
        try:
            retries = 5
            while retries > 0:
                try:
                    with open(lock_file, "x") as _: pass
                    break
                except:
                    time.sleep(0.05)
                    retries -= 1
            with open(self.chat_file, "a") as f:
                f.write(msg)
            if os.path.exists(lock_file): os.remove(lock_file)
        except:
            if os.path.exists(lock_file): os.remove(lock_file)

    def force_heartbeat(self):
        try:
            presence_path = os.path.join(self.presence_dir, self.name)
            data = {'color': self.color, 'last_seen': time.time(), 'status': self.status}
            with open(presence_path, 'w') as f:
                json.dump(data, f)
            self.online_users = self.get_online_users()
            self.update_sidebar()
        except: pass

    async def monitor_messages(self):
        while self.running:
            if os.path.exists(self.chat_file):
                try:
                    with open(self.chat_file, "r") as f:
                        f.seek(self.last_pos)
                        new_lines = f.readlines()
                        if new_lines:
                            for line in new_lines:
                                if line.strip():
                                    self.messages.append(line.strip())
                                    if len(self.messages) > 200: self.messages.pop(0)
                            self.last_pos = f.tell()
                            self.output_field.text = "\n".join(self.messages)
                            self.output_field.buffer.cursor_position = len(self.output_field.text)
                            self.application.invalidate()
                except: pass
            await asyncio.sleep(0.5)

    def run(self):
        print(f"Connecting to: {self.base_dir}")
        self.name = input("Enter your name: ").strip() or "Anonymous"
        
        online = self.get_online_users()
        taken = set()
        for u_data in online.values():
            if isinstance(u_data, dict): taken.add(u_data.get('color'))
            else: taken.add(u_data)
        self.color = next((c for c in COLORS if c not in taken), "white")
        if self.color == "white" and "white" in taken:
             self.color = COLORS[hash(self.name) % len(COLORS)]
        
        if os.path.exists(self.chat_file):
            self.last_pos = max(0, os.path.getsize(self.chat_file) - 5000)

        Thread(target=self.heartbeat, daemon=True).start()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.monitor_messages())
        
        try:
            result = loop.run_until_complete(self.application.run_async())
            if result == 'restart':
                print("\nRestarting...")
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False

if __name__ == "__main__":
    ChatApp().run()
