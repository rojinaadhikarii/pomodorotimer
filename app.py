import os
from pathlib import Path

# App data directory
APP_DIR = Path.home() / ".pomodoro_timer"
APP_DIR.mkdir(parents=True, exist_ok=True)

# Matplotlib cache directory
MPL_CONFIG_DIR = APP_DIR / "matplotlib"
MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

os.environ["MPLCONFIGDIR"] = str(MPL_CONFIG_DIR)

# SQLite database path
DB_PATH = APP_DIR / "pomodoro.db"

import customtkinter as ctk
import tkinter as tk
import sqlite3
import math
import datetime

import matplotlib
matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

ctk.set_appearance_mode("Light")

# Theme colors
COLOR_OFF_WHITE = "#FDFCF8"
COLOR_IVY = "#F3F0E9"
COLOR_NUDE = "#E3DBCC"
COLOR_OBSIDIAN = "#101010"

# Fonts
FONT_TIMER = ("Courier", 44, "bold")
FONT_UI = ("Helvetica", 11, "normal")
FONT_TITLE = ("Courier", 16, "bold")
FONT_SUBTITLE = ("Courier", 14, "bold")


class DatabaseManager:
    def __init__(self, db_name=DB_PATH):
        self.conn = sqlite3.connect(str(db_name))
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    completed INTEGER DEFAULT 0
                )
                """
            )

            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL
                )
                """
            )

    def add_task(self, title):
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO tasks (title, completed) VALUES (?, 0)",
                (title,),
            )
            return cursor.lastrowid

    def get_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, completed FROM tasks")
        return cursor.fetchall()

    def toggle_task(self, task_id, completed_status):
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET completed = ? WHERE id = ?",
                (completed_status, task_id),
            )

    def delete_task(self, task_id):
        with self.conn:
            self.conn.execute(
                "DELETE FROM tasks WHERE id = ?",
                (task_id,),
            )

    def log_session(self, minutes: int):
        today = datetime.date.today().isoformat()

        with self.conn:
            self.conn.execute(
                "INSERT INTO sessions (date, duration_minutes) VALUES (?, ?)",
                (today, minutes),
            )

    def get_weekly_analytics(self):
        today = datetime.date.today()

        dates = [
            (today - datetime.timedelta(days=i)).isoformat()
            for i in range(6, -1, -1)
        ]

        cursor = self.conn.cursor()
        data = {}

        for date_value in dates:
            cursor.execute(
                "SELECT SUM(duration_minutes) FROM sessions WHERE date = ?",
                (date_value,),
            )

            result = cursor.fetchone()[0]

            data[date_value[-5:]] = result if result else 0

        return data

    def get_current_streak(self) -> int:
        cursor = self.conn.cursor()

        cursor.execute(
            "SELECT DISTINCT date FROM sessions ORDER BY date DESC"
        )

        dates = [
            datetime.date.fromisoformat(row[0])
            for row in cursor.fetchall()
        ]

        if not dates:
            return 0

        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)

        if dates[0] != today and dates[0] != yesterday:
            return 0

        streak = 0
        check_date = dates[0]

        for date_value in dates:
            if date_value == check_date:
                streak += 1
                check_date -= datetime.timedelta(days=1)
            else:
                break

        return streak


class PomodoroTimer:
    def __init__(self, root):
        self.root = root

        self.root.title("pomodoro timer")
        self.root.geometry("720x540")
        self.root.configure(fg_color=COLOR_OFF_WHITE)

        self.root.resizable(True, True)
        self.root.minsize(680, 500)

        self.db = DatabaseManager()

        self.reps = 0
        self.timer = None
        self.is_running = False
        self.time_left = 25 * 60
        self.current_mode = "focus"
        self.showing_analytics = False

        self.setup_ui()
        self.load_tasks_from_db()
        self.update_streak_display()

        self.animate_typewriter("focus session")

    def setup_ui(self):
        self.main_container = ctk.CTkFrame(
            self.root,
            fg_color=COLOR_OFF_WHITE,
        )

        self.main_container.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=20,
        )

        # Left pane
        self.left_pane = ctk.CTkFrame(
            self.main_container,
            fg_color=COLOR_OFF_WHITE,
            width=320,
        )

        self.left_pane.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 10),
        )

        self.streak_label = ctk.CTkLabel(
            self.left_pane,
            text="👾 STREAK: 0 DAYS",
            font=("Courier", 12, "bold"),
            text_color=COLOR_OBSIDIAN,
            fg_color=COLOR_IVY,
            corner_radius=8,
            padx=10,
            pady=4,
        )

        self.streak_label.pack(
            pady=(5, 5)
        )

        # Mode selector
        self.mode_frame = ctk.CTkFrame(
            self.left_pane,
            fg_color=COLOR_IVY,
            corner_radius=20,
        )

        self.mode_frame.pack(
            pady=(5, 5)
        )

        self.btn_focus = ctk.CTkButton(
            self.mode_frame,
            text="focus",
            width=70,
            height=26,
            corner_radius=15,
            fg_color=COLOR_OBSIDIAN,
            text_color=COLOR_OFF_WHITE,
            font=("Courier", 11, "bold"),
            command=lambda: self.set_mode("focus"),
        )

        self.btn_focus.grid(
            row=0,
            column=0,
            padx=3,
            pady=3,
        )

        self.btn_short = ctk.CTkButton(
            self.mode_frame,
            text="short break",
            width=85,
            height=26,
            corner_radius=15,
            fg_color="transparent",
            text_color=COLOR_OBSIDIAN,
            font=("Courier", 11, "normal"),
            command=lambda: self.set_mode("short"),
        )

        self.btn_short.grid(
            row=0,
            column=1,
            padx=3,
            pady=3,
        )

        self.btn_long = ctk.CTkButton(
            self.mode_frame,
            text="long break",
            width=85,
            height=26,
            corner_radius=15,
            fg_color="transparent",
            text_color=COLOR_OBSIDIAN,
            font=("Courier", 11, "normal"),
            command=lambda: self.set_mode("long"),
        )

        self.btn_long.grid(
            row=0,
            column=2,
            padx=3,
            pady=3,
        )

        # Title
        self.title_label = ctk.CTkLabel(
            self.left_pane,
            text="",
            font=FONT_TITLE,
            text_color=COLOR_OBSIDIAN,
            fg_color=COLOR_OFF_WHITE,
        )

        self.title_label.pack(
            pady=(5, 5)
        )

        # Timer card
        self.card = tk.Frame(
            self.left_pane,
            bg=COLOR_IVY,
            bd=0,
            highlightthickness=0,
        )

        self.card.pack(
            fill="both",
            expand=True,
            pady=10,
            padx=10,
        )

        self.canvas = tk.Canvas(
            self.card,
            bg=COLOR_IVY,
            highlightthickness=0,
        )

        self.timer_text = self.canvas.create_text(
            0,
            0,
            text="25:00",
            fill=COLOR_OBSIDIAN,
            font=FONT_TIMER,
        )

        self.canvas.pack(
            fill="both",
            expand=True,
        )

        self.canvas.bind(
            "<Configure>",
            self._recenter_timer_text,
        )

        # Timer buttons
        self.button_frame = tk.Frame(
            self.left_pane,
            bg=COLOR_OFF_WHITE,
        )

        self.button_frame.pack(
            pady=10
        )

        self.start_button = tk.Button(
            self.button_frame,
            text="start",
            font=("Courier", 12, "bold"),
            fg=COLOR_OBSIDIAN,
            bg=COLOR_NUDE,
            activebackground=COLOR_IVY,
            activeforeground=COLOR_OBSIDIAN,
            bd=0,
            padx=20,
            pady=8,
            relief="flat",
            command=self.start_timer,
        )

        self.start_button.grid(
            row=0,
            column=0,
            padx=15,
        )

        self.reset_button = tk.Button(
            self.button_frame,
            text="reset",
            font=("Courier", 12, "bold"),
            fg=COLOR_OBSIDIAN,
            bg=COLOR_NUDE,
            activebackground=COLOR_IVY,
            activeforeground=COLOR_OBSIDIAN,
            bd=0,
            padx=20,
            pady=8,
            relief="flat",
            command=self.reset_timer,
        )

        self.reset_button.grid(
            row=0,
            column=1,
            padx=10,
        )

        # Analytics button
        self.analytics_btn = ctk.CTkButton(
            self.left_pane,
            text="📊 see your productivity",
            fg_color="transparent",
            text_color=COLOR_OBSIDIAN,
            hover_color=COLOR_IVY,
            font=("Courier", 11, "underline"),
            command=self.toggle_analytics_view,
        )

        self.analytics_btn.pack(
            pady=(5, 0)
        )

        # Right pane
        self.right_pane = ctk.CTkFrame(
            self.main_container,
            fg_color=COLOR_IVY,
            corner_radius=12,
        )

        self.right_pane.pack(
            side="right",
            fill="both",
            expand=True,
            padx=(10, 0),
        )

        # Task planner
        self.todo_container = ctk.CTkFrame(
            self.right_pane,
            fg_color="transparent",
        )

        self.todo_container.pack(
            fill="both",
            expand=True,
        )

        self.todo_title = ctk.CTkLabel(
            self.todo_container,
            text="task planner",
            font=FONT_SUBTITLE,
            text_color=COLOR_OBSIDIAN,
        )

        self.todo_title.pack(
            pady=(15, 5)
        )

        self.input_frame = ctk.CTkFrame(
            self.todo_container,
            fg_color="transparent",
        )

        self.input_frame.pack(
            fill="x",
            padx=15,
            pady=10,
        )

        self.task_entry = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="add a task",
            fg_color=COLOR_OFF_WHITE,
            text_color=COLOR_OBSIDIAN,
            placeholder_text_color="#888888",
            border_color=COLOR_NUDE,
            border_width=1,
            height=35,
            font=("Courier", 12),
        )

        self.task_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 5),
        )

        self.task_entry.bind(
            "<Return>",
            lambda event: self.add_task(),
        )

        self.add_button = ctk.CTkButton(
            self.input_frame,
            text="+",
            width=35,
            height=35,
            fg_color=COLOR_OBSIDIAN,
            text_color=COLOR_OFF_WHITE,
            hover_color=COLOR_NUDE,
            command=self.add_task,
        )

        self.add_button.pack(
            side="right"
        )

        self.tasks_scrollable = ctk.CTkScrollableFrame(
            self.todo_container,
            fg_color="transparent",
            scrollbar_button_color=COLOR_NUDE,
            scrollbar_button_hover_color=COLOR_OBSIDIAN,
        )

        self.tasks_scrollable.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10),
        )

        # Analytics container
        self.analytics_container = ctk.CTkFrame(
            self.right_pane,
            fg_color="transparent",
        )

    def _recenter_timer_text(self, event):
        self.canvas.coords(
            self.timer_text,
            event.width / 2,
            event.height / 2,
        )

    def set_mode(self, mode: str):
        if self.timer:
            self.root.after_cancel(self.timer)

        self.is_running = False

        self.start_button.config(
            text="start",
            command=self.start_timer,
        )

        self.current_mode = mode

        self.btn_focus.configure(
            fg_color=(
                COLOR_OBSIDIAN
                if mode == "focus"
                else "transparent"
            ),
            text_color=(
                COLOR_OFF_WHITE
                if mode == "focus"
                else COLOR_OBSIDIAN
            ),
            font=(
                "Courier",
                11,
                "bold" if mode == "focus" else "normal",
            ),
        )

        self.btn_short.configure(
            fg_color=(
                COLOR_OBSIDIAN
                if mode == "short"
                else "transparent"
            ),
            text_color=(
                COLOR_OFF_WHITE
                if mode == "short"
                else COLOR_OBSIDIAN
            ),
            font=(
                "Courier",
                11,
                "bold" if mode == "short" else "normal",
            ),
        )

        self.btn_long.configure(
            fg_color=(
                COLOR_OBSIDIAN
                if mode == "long"
                else "transparent"
            ),
            text_color=(
                COLOR_OFF_WHITE
                if mode == "long"
                else COLOR_OBSIDIAN
            ),
            font=(
                "Courier",
                11,
                "bold" if mode == "long" else "normal",
            ),
        )

        if mode == "focus":
            self.time_left = 25 * 60
            self.canvas.itemconfig(
                self.timer_text,
                text="25:00",
            )
            self.animate_typewriter(
                "focus session"
            )

        elif mode == "short":
            self.time_left = 5 * 60
            self.canvas.itemconfig(
                self.timer_text,
                text="05:00",
            )
            self.animate_typewriter(
                "short break"
            )

        elif mode == "long":
            self.time_left = 20 * 60
            self.canvas.itemconfig(
                self.timer_text,
                text="20:00",
            )
            self.animate_typewriter(
                "long break"
            )

    def animate_typewriter(
        self,
        target_text: str,
        current_index=0,
    ):
        if current_index <= len(target_text):
            self.title_label.configure(
                text=target_text[:current_index]
            )

            self.root.after(
                50,
                lambda: self.animate_typewriter(
                    target_text,
                    current_index + 1,
                ),
            )

    def update_streak_display(self):
        streak = self.db.get_current_streak()

        self.streak_label.configure(
            text=f"👾 STREAK: {streak} DAYS"
        )

    def toggle_analytics_view(self):
        if not self.showing_analytics:
            self.todo_container.pack_forget()

            self.analytics_container.pack(
                fill="both",
                expand=True,
                padx=10,
                pady=10,
            )

            self.render_chart()

            self.analytics_btn.configure(
                text="see tasks"
            )

            self.showing_analytics = True

        else:
            self.analytics_container.pack_forget()

            self.todo_container.pack(
                fill="both",
                expand=True,
            )

            self.analytics_btn.configure(
                text="see your productivity"
            )

            self.showing_analytics = False

    def render_chart(self):
        for widget in self.analytics_container.winfo_children():
            widget.destroy()

        data = self.db.get_weekly_analytics()

        dates = list(data.keys())
        minutes = list(data.values())

        fig = Figure(
            figsize=(3.5, 3.8),
            dpi=100,
        )

        fig.patch.set_facecolor(
            COLOR_IVY
        )

        ax = fig.add_subplot(111)

        ax.set_facecolor(
            COLOR_IVY
        )

        ax.yaxis.set_major_locator(
            MaxNLocator(integer=True)
        )

        max_val = (
            max(minutes)
            if minutes
            else 0
        )

        upper_limit = max(
            max_val + 10,
            30,
        )

        ax.set_ylim(
            0,
            upper_limit,
        )

        ax.bar(
            dates,
            minutes,
            color=COLOR_OBSIDIAN,
            width=0.5,
        )

        ax.set_title(
            "focus time (last 7 days)",
            fontsize=12,
            fontweight="bold",
            color=COLOR_OBSIDIAN,
            pad=12,
        )

        ax.set_ylabel(
            "minutes",
            fontsize=9,
            color=COLOR_OBSIDIAN,
        )

        ax.tick_params(
            colors=COLOR_OBSIDIAN,
            labelsize=8,
        )

        ax.spines["top"].set_visible(
            False
        )

        ax.spines["right"].set_visible(
            False
        )

        ax.spines["left"].set_color(
            COLOR_NUDE
        )

        ax.spines["bottom"].set_color(
            COLOR_NUDE
        )

        fig.tight_layout()

        canvas = FigureCanvasTkAgg(
            fig,
            master=self.analytics_container,
        )

        canvas.draw()

        canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

    def load_tasks_from_db(self):
        for widget in self.tasks_scrollable.winfo_children():
            widget.destroy()

        tasks = self.db.get_tasks()

        for task_id, title, completed in tasks:
            self.render_task_item(
                task_id,
                title,
                completed,
            )

    def render_task_item(
        self,
        task_id,
        title,
        completed,
    ):
        row_frame = ctk.CTkFrame(
            self.tasks_scrollable,
            fg_color=COLOR_OFF_WHITE,
            corner_radius=6,
        )

        row_frame.pack(
            fill="x",
            pady=4,
            padx=2,
        )

        check_var = ctk.IntVar(
            value=completed
        )

        checkbox = ctk.CTkCheckBox(
            row_frame,
            text=title,
            variable=check_var,
            text_color=(
                COLOR_OBSIDIAN
                if not completed
                else "#888888"
            ),
            fg_color=COLOR_OBSIDIAN,
            bg_color="transparent",
            hover_color=COLOR_NUDE,
            border_color=COLOR_OBSIDIAN,
            font=(
                "Courier",
                12,
                "overstrike"
                if completed
                else "normal",
            ),
            command=lambda: self.toggle_task(
                task_id,
                check_var.get(),
                checkbox,
            ),
        )

        checkbox.pack(
            side="left",
            padx=10,
            pady=8,
        )

        delete_btn = ctk.CTkButton(
            row_frame,
            text="x",
            width=20,
            height=20,
            fg_color="transparent",
            text_color="#888888",
            hover_color=COLOR_IVY,
            command=lambda: self.delete_task(
                task_id,
                row_frame,
            ),
        )

        delete_btn.pack(
            side="right",
            padx=8,
        )

    def add_task(self):
        title = self.task_entry.get().strip()

        if title:
            task_id = self.db.add_task(
                title
            )

            self.render_task_item(
                task_id,
                title,
                0,
            )

            self.task_entry.delete(
                0,
                "end",
            )

    def toggle_task(
        self,
        task_id,
        is_completed,
        checkbox_widget,
    ):
        self.db.toggle_task(
            task_id,
            is_completed,
        )

        if is_completed:
            checkbox_widget.configure(
                text_color="#888888",
                font=(
                    "Courier",
                    12,
                    "overstrike",
                ),
            )

        else:
            checkbox_widget.configure(
                text_color=COLOR_OBSIDIAN,
                font=(
                    "Courier",
                    12,
                    "normal",
                ),
            )

    def delete_task(
        self,
        task_id,
        row_widget,
    ):
        self.db.delete_task(
            task_id
        )

        row_widget.destroy()

    def start_timer(self):
        if not self.is_running:
            self.is_running = True

            self.start_button.config(
                text="pause",
                command=self.pause_timer,
            )

            self.count_down()

    def pause_timer(self):
        if self.is_running:
            self.is_running = False

            if self.timer:
                self.root.after_cancel(
                    self.timer
                )

            self.start_button.config(
                text="start",
                command=self.start_timer,
            )

    def reset_timer(self):
        self.set_mode(
            self.current_mode
        )

    def count_down(self):
        minutes = math.floor(
            self.time_left / 60
        )

        seconds = (
            self.time_left % 60
        )

        if seconds < 10:
            seconds = f"0{seconds}"

        self.canvas.itemconfig(
            self.timer_text,
            text=f"{minutes}:{seconds}",
        )

        if self.time_left > 0:
            self.time_left -= 1

            self.timer = self.root.after(
                1000,
                self.count_down,
            )

        else:
            self.is_running = False

            if self.current_mode == "focus":
                self.db.log_session(25)
                self.update_streak_display()

            self.reps += 1
            self.switch_session()

    def switch_session(self):
        if self.reps % 8 == 0:
            self.set_mode("long")

        elif self.reps % 2 == 0:
            self.set_mode("focus")

        else:
            self.set_mode("short")

        self.start_timer()


if __name__ == "__main__":
    root = ctk.CTk()
    app = PomodoroTimer(root)
    root.mainloop()