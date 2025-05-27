import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import requests
import json
import threading
import queue
import os
import sys

# --- Базовый промпт для LLM ---
BASE_SYSTEM_PROMPT = """Ты — продвинутый ИИ-ассистент по программированию, интегрированный в инструмент для разработки. Твоя основная задача — помогать пользователю писать, анализировать, исправлять и оптимизировать код.
Ты должен:
1.  Внимательно анализировать предоставленный код и контекст.
2.  Предоставлять четкие, точные и релевантные ответы или фрагменты кода.
3.  Если тебя просят исправить ошибку, объясни причину ошибки (если это уместно) и предложи корректный вариант.
4.  Если тебя просят написать новый код, старайся следовать лучшим практикам и предоставленному стилю кодирования.
5.  Если тебя просят модифицировать существующий код, сохрани остальную часть кода без изменений, если не указано иное.
6.  Будь готов работать с различными языками программирования.
7.  Твои ответы должны быть в основном кодом или объяснениями, связанными с кодом. Избегай лишних разговоров.
8.  При модификации файла, возвращай ТОЛЬКО ИЗМЕНЕННЫЙ КОД ФАЙЛА ЦЕЛИКОМ, без дополнительных пояснений или фраз вроде "Вот исправленный код:". Если пользователь просит объяснить, он сделает это отдельным запросом.
Помни, что точность критически важна.
"""

CONFIG_FILE_NAME = "ollama_assistant_session.json"

class OllamaCodeAssistant:
    def __init__(self, root):
        self.root = root
        self.root.title("Ollama Code Assistant")
        self.root.geometry("1300x900")

        self.ollama_model = "deepseek-coder-v2:16b"
        self.ollama_chat_api_url = "http://localhost:11434/api/chat"

        self.project_files = {} # {filepath: content}
        self.current_target_file_path = None
        self.context_file_paths = set()
        self.ollama_response_queue = queue.Queue()
        self.last_browsed_path = os.path.expanduser("~") # Default to home directory
        self.last_opened_project_root = None # For restoring directory view

        # --- Шрифты (вдохновлено Authkit: Inter, Segoe UI) ---
        self.ui_font_family_preferred = "Inter"
        self.ui_font_family_fallback1 = "Segoe UI"
        self.ui_font_family_fallback2 = "Arial"
        self.code_font_family = "Consolas"
        self.ui_font_size = 10
        self.code_font_size = 11

        self.ui_font_family = self.ui_font_family_fallback2 # Default to Arial
        try:
            root.tk.call('font', 'metrics', (self.ui_font_family_preferred, self.ui_font_size))
            self.ui_font_family = self.ui_font_family_preferred
        except tk.TclError:
            try:
                root.tk.call('font', 'metrics', (self.ui_font_family_fallback1, self.ui_font_size))
                self.ui_font_family = self.ui_font_family_fallback1
            except tk.TclError:
                print(f"Шрифты '{self.ui_font_family_preferred}' и '{self.ui_font_family_fallback1}' не найдены, используется '{self.ui_font_family_fallback2}'.")
        
        self.ui_font = (self.ui_font_family, self.ui_font_size)
        self.ui_font_bold = (self.ui_font_family, self.ui_font_size, "bold")
        self.code_font = (self.code_font_family, self.code_font_size)

        # --- Стилизация (вдохновлено Authkit.com) ---
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            print("Тема 'clam' не найдена.")

        # Цветовая схема Authkit (адаптированная)
        self.bg_color = "#F9FAFB" # Очень светлый серый / почти белый
        self.fg_color = "#1F2937" # Темно-серый для текста
        self.text_bg_color = "#FFFFFF" # Белый для полей ввода
        self.text_fg_color = "#111827" # Очень темный серый для текста в полях
        self.border_color = "#D1D5DB" # Светло-серый для границ
        
        self.accent_color = "#6D28D9" # Фиолетовый (Authkit Purple 700)
        self.accent_hover_color = "#5B21B6" # Темнее фиолетовый для ховера
        self.button_fg_color = "#FFFFFF" # Белый текст на акцентных кнопках

        self.tree_selected_bg_color = self.accent_color
        self.tree_selected_fg_color = "#FFFFFF"
        self.tree_heading_bg = "#F3F4F6" # Очень светлый серый для заголовков
        self.tree_heading_fg = self.fg_color

        self.root.configure(bg=self.bg_color)

        self.style.configure("TLabel", background=self.bg_color, foreground=self.fg_color, padding=6, font=self.ui_font)
        self.style.configure("TButton", foreground=self.fg_color, background=self.bg_color, 
                             padding=(10, 8), font=self.ui_font_bold, borderwidth=1, relief="solid", bordercolor=self.border_color)
        self.style.map("TButton",
                       background=[('active', "#E5E7EB"), ('pressed', "#D1D5DB")], # Светло-серые для обычных кнопок
                       bordercolor=[('active', self.accent_color)])

        # Акцентная кнопка
        self.style.configure("Accent.TButton", foreground=self.button_fg_color, background=self.accent_color, bordercolor=self.accent_color)
        self.style.map("Accent.TButton",
                       background=[('active', self.accent_hover_color), ('pressed', self.accent_hover_color)],
                       bordercolor=[('active', self.accent_hover_color)])


        self.style.configure("TFrame", background=self.bg_color)
        
        self.style.configure("Treeview",
                             background=self.text_bg_color, foreground=self.text_fg_color,
                             fieldbackground=self.text_bg_color, font=self.ui_font,
                             rowheight=28, borderwidth=1, relief="solid")
        self.style.map("Treeview",
                       background=[('selected', self.tree_selected_bg_color)],
                       foreground=[('selected', self.tree_selected_fg_color)])
        self.style.configure("Treeview.Heading",
                             background=self.tree_heading_bg, foreground=self.tree_heading_fg,
                             font=self.ui_font_bold, padding=8, relief="flat", borderwidth=0)
        
        self.style.configure("Vertical.TScrollbar", background=self.bg_color, troughcolor=self.tree_heading_bg, bordercolor=self.border_color, arrowcolor=self.fg_color, relief="flat")
        self.style.configure("Horizontal.TScrollbar", background=self.bg_color, troughcolor=self.tree_heading_bg, bordercolor=self.border_color, arrowcolor=self.fg_color, relief="flat")
        
        self.style.configure("TPanedwindow", background=self.border_color)
        self.style.configure("TPanedwindow.Sash", sashthickness=8, background=self.bg_color, relief="flat")

        self._setup_ui()
        self._load_session()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_ollama_queue)

    def _get_config_path(self):
        # Сохраняем конфиг рядом со скриптом
        base_path = os.path.dirname(os.path.abspath(sys.argv[0] if hasattr(sys, 'frozen') else __file__))
        return os.path.join(base_path, CONFIG_FILE_NAME)

    def _load_session(self):
        config_path = self._get_config_path()
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.last_browsed_path = config.get("last_browsed_path", os.path.expanduser("~"))
                self.last_opened_project_root = config.get("last_opened_project_root")
                
                context_files = config.get("context_file_paths", [])
                self.context_file_paths = set(cf for cf in context_files if os.path.exists(cf)) # Проверяем существование

                last_target_file = config.get("current_target_file_path")

                if self.last_opened_project_root and os.path.isdir(self.last_opened_project_root):
                    self._clear_file_tree()
                    self._populate_tree_with_directory(self.last_opened_project_root)
                
                if last_target_file and os.path.isfile(last_target_file):
                    self._load_file_to_editor(last_target_file)
                    # Попытка выделить файл в дереве, если его родительская папка открыта
                    if self.file_tree.exists(last_target_file):
                        self.file_tree.selection_set(last_target_file)
                        self.file_tree.focus(last_target_file)
                        self.file_tree.see(last_target_file)
                    elif not self.last_opened_project_root: # Если не открывали проект, но был файл
                        self._add_single_file_to_tree(last_target_file, select_it=True)

                llm_prompt = config.get("llm_prompt_input", "")
                self.llm_prompt_input.delete("1.0", tk.END)
                self.llm_prompt_input.insert("1.0", llm_prompt)

                self._update_status("Сессия загружена.")
                return True
        except Exception as e:
            print(f"Ошибка загрузки сессии: {e}")
            self._update_status("Ошибка загрузки предыдущей сессии.")
        return False

    def _save_session(self):
        config = {
            "current_target_file_path": self.current_target_file_path,
            "context_file_paths": list(self.context_file_paths),
            "last_browsed_path": self.last_browsed_path,
            "last_opened_project_root": self.last_opened_project_root,
            "llm_prompt_input": self.llm_prompt_input.get("1.0", tk.END).strip()
        }
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            self._update_status("Сессия сохранена.")
        except Exception as e:
            print(f"Ошибка сохранения сессии: {e}")
            self._update_status("Ошибка сохранения сессии.")

    def _on_close(self):
        self._save_session()
        self.root.destroy()

    def _setup_ui(self):
        menubar = tk.Menu(self.root, bg=self.bg_color, fg=self.fg_color, activebackground=self.accent_color, activeforeground=self.button_fg_color, relief=tk.FLAT, font=self.ui_font)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color, activebackground=self.accent_color, activeforeground=self.button_fg_color, font=self.ui_font)
        file_menu.add_command(label="Открыть файл...", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Открыть директорию...", command=self._open_directory, accelerator="Ctrl+Shift+O")
        file_menu.add_command(label="Сохранить текущий файл", command=self._save_current_file, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_close)
        menubar.add_cascade(label="Файл", menu=file_menu)

        context_menu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color, activebackground=self.accent_color, activeforeground=self.button_fg_color, font=self.ui_font)
        context_menu.add_command(label="Управление контекстными файлами", command=self._manage_context_files_dialog)
        menubar.add_cascade(label="Контекст", menu=context_menu)
        
        self.root.bind_all("<Control-o>", lambda event: self._open_file())
        self.root.bind_all("<Control-Shift-o>", lambda event: self._open_directory()) # Changed to lowercase 'o'
        self.root.bind_all("<Control-s>", lambda event: self._save_current_file())

        main_paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL, style="TPanedwindow")
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=15, pady=15) # Увеличены отступы

        left_frame = ttk.Frame(main_paned_window, width=400) # Шире
        main_paned_window.add(left_frame, weight=1)

        fm_label = ttk.Label(left_frame, text="Проводник") # Изменено название
        fm_label.pack(pady=(5, 10), anchor="w", padx=10)

        tree_container = ttk.Frame(left_frame, style="Card.TFrame") # Обертка для границ
        tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        self.style.configure("Card.TFrame", background=self.text_bg_color, relief="solid", borderwidth=1, bordercolor=self.border_color)


        self.file_tree = ttk.Treeview(tree_container, selectmode="browse", show="tree headings")
        self.file_tree["columns"] = ("fullpath",)
        self.file_tree.column("#0", width=300, minwidth=250, stretch=tk.YES) 
        self.file_tree.column("fullpath", width=0, minwidth=0, stretch=tk.NO) 
        self.file_tree.heading("#0", text="Имя файла / Директория", anchor=tk.W)
        
        tree_ysb = ttk.Scrollbar(tree_container, orient="vertical", command=self.file_tree.yview, style="Vertical.TScrollbar")
        tree_xsb = ttk.Scrollbar(tree_container, orient="horizontal", command=self.file_tree.xview, style="Horizontal.TScrollbar")
        self.file_tree.configure(yscrollcommand=tree_ysb.set, xscrollcommand=tree_xsb.set)

        tree_ysb.pack(side=tk.RIGHT, fill=tk.Y)
        tree_xsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.file_tree.pack(fill=tk.BOTH, expand=True, padx=1, pady=1) # Небольшой отступ внутри рамки
        
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_tree_select)
        self.file_tree.bind("<Double-1>", self._on_file_tree_double_click)


        right_paned_window = ttk.PanedWindow(main_paned_window, orient=tk.VERTICAL, style="TPanedwindow")
        main_paned_window.add(right_paned_window, weight=3)

        editor_frame_outer = ttk.Frame(right_paned_window) # Внешний фрейм для отступов
        right_paned_window.add(editor_frame_outer, weight=3)
        editor_label = ttk.Label(editor_frame_outer, text="Редактор:")
        editor_label.pack(pady=(5, 5), anchor="w", padx=10)
        
        editor_container = ttk.Frame(editor_frame_outer, style="Card.TFrame") # Обертка для границ
        editor_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        self.code_editor = scrolledtext.ScrolledText(editor_container, wrap=tk.WORD, undo=True,
                                                     bg=self.text_bg_color, fg=self.text_fg_color,
                                                     selectbackground=self.accent_color, selectforeground=self.button_fg_color,
                                                     insertbackground=self.fg_color, font=self.code_font,
                                                     padx=15, pady=15, # Увеличены внутренние отступы
                                                     borderwidth=0, relief="flat")
        self.code_editor.pack(fill=tk.BOTH, expand=True)


        llm_frame_outer = ttk.Frame(right_paned_window) # Внешний фрейм
        right_paned_window.add(llm_frame_outer, weight=2)

        llm_prompt_label = ttk.Label(llm_frame_outer, text="Ваш запрос к LLM:")
        llm_prompt_label.pack(pady=(10, 5), anchor="w", padx=10)
        
        prompt_container = ttk.Frame(llm_frame_outer, style="Card.TFrame")
        prompt_container.pack(fill=tk.X, expand=False, padx=10)
        self.llm_prompt_input = scrolledtext.ScrolledText(prompt_container, wrap=tk.WORD, height=5,
                                                          bg=self.text_bg_color, fg=self.text_fg_color,
                                                          selectbackground=self.accent_color, selectforeground=self.button_fg_color,
                                                          insertbackground=self.fg_color, font=self.ui_font,
                                                          padx=15, pady=15, borderwidth=0, relief="flat")
        self.llm_prompt_input.pack(fill=tk.X, expand=True)

        llm_buttons_frame = ttk.Frame(llm_frame_outer)
        llm_buttons_frame.pack(fill=tk.X, pady=15, padx=10) # Увеличен отступ
        ttk.Button(llm_buttons_frame, text="Общий запрос", command=lambda: self._send_to_ollama(action="general"), style="Accent.TButton").pack(side=tk.LEFT, padx=(0,10))
        ttk.Button(llm_buttons_frame, text="Исправить/Дополнить файл", command=lambda: self._send_to_ollama(action="modify"), style="Accent.TButton").pack(side=tk.LEFT)

        self.llm_response_label = ttk.Label(llm_frame_outer, text="Ответ от LLM:")
        self.llm_response_label.pack(pady=(5, 5), anchor="w", padx=10)
        
        response_container = ttk.Frame(llm_frame_outer, style="Card.TFrame")
        response_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        self.llm_response_output = scrolledtext.ScrolledText(response_container, wrap=tk.WORD, state=tk.DISABLED,
                                                             bg=self.text_bg_color, fg=self.text_fg_color,
                                                             font=self.code_font,
                                                             padx=15, pady=15, borderwidth=0, relief="flat")
        self.llm_response_output.pack(fill=tk.BOTH, expand=True)

        llm_apply_button = ttk.Button(llm_frame_outer, text="Применить изменения в редактор", command=self._apply_llm_response_to_editor, style="TButton")
        llm_apply_button.pack(pady=(10,15), padx=10, anchor="e") # Справа

        self.status_bar = ttk.Label(self.root, text="Готово", relief=tk.FLAT, anchor=tk.W, padding=(10,5), background=self.tree_heading_bg, foreground=self.fg_color)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _update_status(self, message):
        self.status_bar.config(text=message)
        self.root.update_idletasks()

    def _get_initial_dir(self):
        if self.current_target_file_path and os.path.exists(os.path.dirname(self.current_target_file_path)):
            return os.path.dirname(self.current_target_file_path)
        if self.last_browsed_path and os.path.exists(self.last_browsed_path):
            return self.last_browsed_path
        return os.path.expanduser("~")

    def _add_single_file_to_tree(self, filepath, select_it=False):
        filename = os.path.basename(filepath)
        iid = filepath 
        
        parent_dir_node_id = "открытые_файлы_категория"
        parent_dir_node_text = "Отдельно открытые файлы"

        if not self.file_tree.exists(parent_dir_node_id):
            self.file_tree.insert("", "end", iid=parent_dir_node_id, text=parent_dir_node_text, open=True, values=("",)) # values must be a tuple

        file_exists_in_tree = False
        for item in self.file_tree.get_children(parent_dir_node_id):
            # Check if values is not empty and then access its first element
            item_values = self.file_tree.item(item, "values")
            if item_values and item_values[0] == filepath:
                file_exists_in_tree = True
                if select_it:
                    self.file_tree.selection_set(item)
                    self.file_tree.focus(item)
                    self.file_tree.see(item)
                break
        
        if not file_exists_in_tree:
            item_id = self.file_tree.insert(parent_dir_node_id, "end", iid=iid, text=filename, values=(filepath,)) # Ensure values is a tuple
            if select_it:
                self.file_tree.selection_set(item_id)
                self.file_tree.focus(item_id)
                self.file_tree.see(item_id)


    def _open_file(self):
        initial_dir = self._get_initial_dir()
        filepath = filedialog.askopenfilename(initialdir=initial_dir, parent=self.root,
                                             defaultextension=".*",
                                             filetypes=[("All files", "*.*"), ("Python files", "*.py"), 
                                                        ("Text files", "*.txt"), ("Markdown", "*.md")])
        if filepath:
            self.last_browsed_path = os.path.dirname(filepath)
            self._load_file_to_editor(filepath)
            # Если файл не является частью текущего отображаемого проекта, добавляем его отдельно
            if not self.file_tree.exists(filepath):
                 self._add_single_file_to_tree(filepath, select_it=True)
            else: # Если файл уже в дереве (например, из открытой папки), просто выделяем его
                self.file_tree.selection_set(filepath)
                self.file_tree.focus(filepath)
                self.file_tree.see(filepath)


    def _clear_file_tree(self):
        for i in self.file_tree.get_children():
            self.file_tree.delete(i)

    def _populate_tree_with_directory(self, dirpath):
        self.last_opened_project_root = dirpath # Сохраняем корень проекта
        dir_name = os.path.basename(dirpath)
        root_node_iid = dirpath 
        root_node = self.file_tree.insert("", "end", iid=root_node_iid, text=dir_name, values=(dirpath,), open=True)
        self._populate_file_tree_recursive(dirpath, root_node)


    def _open_directory(self):
        initial_dir = self._get_initial_dir()
        dirpath = filedialog.askdirectory(initialdir=initial_dir, parent=self.root, mustexist=True)
        if dirpath:
            self.last_browsed_path = dirpath
            self._clear_file_tree()
            self.project_files.clear() # Очищаем кэш файлов при открытии новой директории
            self.current_target_file_path = None # Сбрасываем текущий файл
            self.code_editor.delete('1.0', tk.END) # Очищаем редактор
            self.root.title("Ollama Code Assistant")

            self._populate_tree_with_directory(dirpath)
            self._update_status(f"Директория открыта: {dirpath}")


    def _populate_file_tree_recursive(self, current_path, parent_node_iid):
        try:
            items = sorted(os.listdir(current_path), key=lambda x: (not os.path.isdir(os.path.join(current_path, x)), x.lower()))
            for item_name in items:
                item_path = os.path.join(current_path, item_name)
                node_iid = item_path 
                if os.path.isdir(item_path):
                    node = self.file_tree.insert(parent_node_iid, "end", iid=node_iid, text=item_name, values=(item_path,), open=False)
                    self._populate_file_tree_recursive(item_path, node)
                else:
                    self.file_tree.insert(parent_node_iid, "end", iid=node_iid, text=item_name, values=(item_path,))
        except OSError as e:
            print(f"Ошибка доступа к {current_path}: {e}")
            self._update_status(f"Ошибка доступа: {current_path}")

    def _on_file_tree_double_click(self, event):
        item_id = self.file_tree.focus()
        if not item_id: return
        
        item_values = self.file_tree.item(item_id, "values")
        if not item_values or not item_values[0]: return # Проверка, что values не пуст

        filepath = item_values[0]
        if os.path.isdir(filepath):
            self.file_tree.item(item_id, open=not self.file_tree.item(item_id, "open"))
        elif os.path.isfile(filepath):
             self._load_file_to_editor(filepath)

    def _on_file_tree_select(self, event):
        selected_item_ids = self.file_tree.selection()
        if not selected_item_ids: return
        
        selected_item_id = selected_item_ids[0]
        item_values = self.file_tree.item(selected_item_id, "values")

        if not item_values or not item_values[0]: return

        filepath = item_values[0]
        if os.path.isfile(filepath):
            self._load_file_to_editor(filepath)
        elif os.path.isdir(filepath):
            self._update_status(f"Выбрана директория: {os.path.basename(filepath)}")

    def _load_file_to_editor(self, filepath):
        try:
            # Проверяем, существует ли файл перед чтением
            if not os.path.isfile(filepath):
                messagebox.showerror("Файл не найден", f"Файл {filepath} больше не существует.", parent=self.root)
                self._update_status(f"Ошибка: Файл {filepath} не найден.")
                # Попытаться удалить из project_files и, возможно, из дерева, если он там есть как одиночный
                if filepath in self.project_files:
                    del self.project_files[filepath]
                if self.file_tree.exists(filepath): # Если это iid элемента
                    # Дополнительно проверить, не является ли он частью "Отдельно открытые файлы"
                    parent_of_item = self.file_tree.parent(filepath)
                    if parent_of_item == "открытые_файлы_категория":
                        self.file_tree.delete(filepath)
                return

            # Загрузка или обновление из кэша, если файл изменился
            file_modified_time = os.path.getmtime(filepath)
            cached_content, cached_mtime = self.project_files.get(filepath, (None, 0))

            if cached_content is None or file_modified_time > cached_mtime:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.project_files[filepath] = (content, file_modified_time)
            else:
                content = cached_content
            
            self.current_target_file_path = filepath
            self.last_browsed_path = os.path.dirname(filepath) # Обновляем для диалогов
            
            self.code_editor.config(state=tk.NORMAL)
            self.code_editor.delete('1.0', tk.END)
            self.code_editor.insert('1.0', content)
            # self.code_editor.config(state=tk.DISABLED) # Если нужно сделать read-only до явного редактирования

            self._update_status(f"Открыт: {os.path.basename(filepath)}")
            self.root.title(f"Ollama Code Assistant - {os.path.basename(filepath)}")
        except Exception as e:
            messagebox.showerror("Ошибка загрузки файла", f"Не удалось загрузить файл {filepath}: {e}", parent=self.root)
            self._update_status(f"Ошибка загрузки файла: {filepath}")

    def _save_current_file(self):
        if not self.current_target_file_path:
            messagebox.showwarning("Нет файла", "Сначала откройте или выберите файл для сохранения.", parent=self.root)
            return

        content_to_save = self.code_editor.get('1.0', tk.END).strip()
        try:
            with open(self.current_target_file_path, 'w', encoding='utf-8') as f:
                f.write(content_to_save)
            
            # Обновляем кэш с новым временем модификации
            new_mtime = os.path.getmtime(self.current_target_file_path)
            self.project_files[self.current_target_file_path] = (content_to_save, new_mtime)
            self._update_status(f"Файл сохранен: {self.current_target_file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файл: {e}", parent=self.root)
            self._update_status(f"Ошибка сохранения файла: {self.current_target_file_path}")

    def _manage_context_files_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Управление контекстными файлами")
        dialog.geometry("750x550")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True) # Разрешаем изменять размер

        ttk.Label(dialog, text="Выберите файлы для использования в качестве контекста:", font=self.ui_font_bold).pack(pady=15, padx=15, anchor="w")

        listbox_container = ttk.Frame(dialog, style="Card.TFrame")
        listbox_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0,10))

        self.context_listbox = tk.Listbox(listbox_container, selectmode=tk.MULTIPLE,
                                          bg=self.text_bg_color, fg=self.text_fg_color,
                                          selectbackground=self.tree_selected_bg_color, 
                                          selectforeground=self.tree_selected_fg_color,
                                          font=self.ui_font, borderwidth=0, relief="flat", activestyle="none",
                                          highlightthickness=0)
        self.context_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        scrollbar = ttk.Scrollbar(listbox_container, orient=tk.VERTICAL, command=self.context_listbox.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.context_listbox.config(yscrollcommand=scrollbar.set)
        
        all_available_files = set()
        def get_all_files_from_tree(parent_item=""):
            for item_id in self.file_tree.get_children(parent_item):
                values = self.file_tree.item(item_id, "values")
                if values and values[0] and os.path.isfile(values[0]):
                    all_available_files.add(values[0])
                if self.file_tree.get_children(item_id): # Рекурсия
                     get_all_files_from_tree(item_id)
        get_all_files_from_tree()
        
        # Добавляем файлы из project_files, которые могли быть открыты отдельно и еще не в дереве
        for path_key in self.project_files:
            if os.path.isfile(path_key): # path_key это сам путь
                all_available_files.add(path_key)

        # Используем self.current_target_file_path для определения базового пути для relpath
        base_path_for_relpath = os.path.dirname(self.current_target_file_path) if self.current_target_file_path else self.last_browsed_path

        sorted_files = sorted(list(all_available_files))
        self.dialog_sorted_files_map = {idx: path for idx, path in enumerate(sorted_files)} # Для обратного маппинга


        for idx, filepath in enumerate(sorted_files):
            try:
                if base_path_for_relpath and os.path.commonpath([filepath, base_path_for_relpath]) == base_path_for_relpath:
                     display_name = os.path.relpath(filepath, start=base_path_for_relpath)
                else: # Если пути на разных дисках или base_path_for_relpath не установлен
                    display_name = filepath 
                
                if len(display_name) > 80: # Обрезаем слишком длинные пути
                    display_name = os.path.basename(filepath) + f" (...{os.path.basename(os.path.dirname(filepath))})"
            except ValueError:
                 display_name = filepath # Полный путь, если relpath не удался

            self.context_listbox.insert(tk.END, display_name)
            if filepath in self.context_file_paths:
                self.context_listbox.selection_set(idx)

        def on_ok():
            self.context_file_paths.clear()
            selected_indices = self.context_listbox.curselection()
            for idx in selected_indices:
                actual_filepath = self.dialog_sorted_files_map.get(idx)
                if actual_filepath:
                    self.context_file_paths.add(actual_filepath)
            self._update_status(f"Контекстные файлы обновлены: {len(self.context_file_paths)} файлов")
            dialog.destroy()

        buttons_frame = ttk.Frame(dialog)
        buttons_frame.pack(pady=15, padx=15, side=tk.BOTTOM, fill=tk.X)
        ttk.Button(buttons_frame, text="OK", command=on_ok, style="Accent.TButton").pack(side=tk.RIGHT, padx=(10,0))
        ttk.Button(buttons_frame, text="Отмена", command=dialog.destroy, style="TButton").pack(side=tk.RIGHT)


    def _send_to_ollama(self, action="general"):
        user_prompt_text = self.llm_prompt_input.get("1.0", tk.END).strip()
        
        if not user_prompt_text and action == "general":
            messagebox.showwarning("Пустой запрос", "Пожалуйста, введите ваш запрос к LLM.", parent=self.root)
            return

        if action == "modify" and not self.current_target_file_path:
            messagebox.showwarning("Нет целевого файла", "Пожалуйста, выберите или откройте файл для модификации.", parent=self.root)
            return

        self._update_status("Отправка запроса к Ollama...")
        self.llm_response_output.config(state=tk.NORMAL)
        self.llm_response_output.delete("1.0", tk.END)
        self.llm_response_output.insert(tk.END, "Обработка...\n")
        self.llm_response_output.config(state=tk.DISABLED)

        context_data = []
        for ctx_path in self.context_file_paths:
            if ctx_path == self.current_target_file_path and action == "modify":
                continue
            
            file_content_tuple = self.project_files.get(ctx_path)
            file_content = None
            if file_content_tuple:
                file_content = file_content_tuple[0] # Берем контент из кортежа
            elif os.path.exists(ctx_path): # Если файла нет в кэше, но он есть в списке контекста, пробуем загрузить
                 try:
                    with open(ctx_path, 'r', encoding='utf-8') as f_ctx:
                        file_content = f_ctx.read()
                    self.project_files[ctx_path] = (file_content, os.path.getmtime(ctx_path)) # Кэшируем с mtime
                 except Exception as e:
                    print(f"Не удалось прочитать контекстный файл {ctx_path}: {e}")
            
            if file_content is not None:
                context_data.append({
                    "filename": os.path.basename(ctx_path),
                    "content": file_content
                })

        messages = [{"role": "system", "content": BASE_SYSTEM_PROMPT}]

        if context_data:
            context_str_parts = ["Контекст из других файлов:\n"]
            for item in context_data:
                context_str_parts.append(f"--- BEGIN CONTEXT FILE: {item['filename']} ---\n{item['content']}\n--- END CONTEXT FILE: {item['filename']} ---\n")
            messages.append({"role": "user", "content": "\n".join(context_str_parts)})

        target_file_content_tuple = self.project_files.get(self.current_target_file_path)
        target_file_content = target_file_content_tuple[0] if target_file_content_tuple else ""
        
        # Всегда берем актуальный текст из редактора, если это целевой файл
        if self.current_target_file_path:
            target_file_content = self.code_editor.get("1.0", tk.END).strip()


        user_query_message_content = ""
        if action == "modify":
            if not target_file_content and self.current_target_file_path: # Проверяем, что файл не пуст, если он выбран
                 messagebox.showwarning("Пустой файл", "Целевой файл пуст. Нечего модифицировать.", parent=self.root)
                 self._update_status("Ошибка: целевой файл пуст.")
                 return

            user_query_message_content = (
                f"Текущий файл для модификации ({os.path.basename(self.current_target_file_path)}):\n"
                f"--- BEGIN TARGET FILE ---\n{target_file_content}\n--- END TARGET FILE ---\n\n"
                f"Задание от пользователя: {user_prompt_text}\n\n"
                f"Пожалуйста, верни ТОЛЬКО полный обновленный код для файла {os.path.basename(self.current_target_file_path)}. "
                "Не добавляй никаких объяснений, markdown форматирования или вводных фраз перед кодом или после него."
            )
        else: # general action
            if target_file_content and self.current_target_file_path:
                 user_query_message_content = (
                     f"Содержимое текущего активного файла ({os.path.basename(self.current_target_file_path)}):\n"
                     f"{target_file_content}\n\n"
                     f"Запрос: {user_prompt_text}"
                 )
            else:
                 user_query_message_content = user_prompt_text
        
        messages.append({"role": "user", "content": user_query_message_content})

        payload = { "model": self.ollama_model, "messages": messages, "stream": True }
        
        thread = threading.Thread(target=self._ollama_request_thread, args=(payload,))
        thread.daemon = True
        thread.start()

    def _ollama_request_thread(self, payload):
        try:
            response = requests.post(self.ollama_chat_api_url, json=payload, stream=True, timeout=180) # Таймаут 3 минуты
            response.raise_for_status()
            full_response_content = ""
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    try:
                        json_chunk = json.loads(decoded_line)
                        if 'message' in json_chunk and 'content' in json_chunk['message']:
                            content_part = json_chunk['message']['content']
                            full_response_content += content_part
                            self.ollama_response_queue.put(("chunk", content_part))
                        if json_chunk.get("done"): break
                    except json.JSONDecodeError:
                        print(f"Пропуск невалидного JSON-чанка: {decoded_line}")
            self.ollama_response_queue.put(("done", full_response_content))
        except requests.exceptions.Timeout:
            self.ollama_response_queue.put(("error", "Ошибка: Запрос к Ollama превысил время ожидания."))
        except requests.exceptions.RequestException as e:
            self.ollama_response_queue.put(("error", f"Ошибка соединения с Ollama: {e}"))
        except Exception as e:
            self.ollama_response_queue.put(("error", f"Неизвестная ошибка при запросе к Ollama: {e}"))

    def _process_ollama_queue(self):
        try:
            while True:
                message_type, data = self.ollama_response_queue.get_nowait()
                self.llm_response_output.config(state=tk.NORMAL)
                if message_type == "chunk":
                    if self.llm_response_output.get("1.0", tk.END).strip() == "Обработка...":
                        self.llm_response_output.delete("1.0", tk.END)
                    self.llm_response_output.insert(tk.END, data)
                    self.llm_response_output.see(tk.END)
                elif message_type == "done":
                    self._update_status("Ответ от Ollama получен.")
                    current_text = self.llm_response_output.get("1.0", tk.END).strip()
                    if current_text == "Обработка..." and not data:
                         self.llm_response_output.delete("1.0", tk.END)
                    elif current_text == "Обработка..." and data: # Если был только один чанк "done"
                        self.llm_response_output.delete("1.0", tk.END)
                        self.llm_response_output.insert(tk.END, data)
                    self.llm_response_output.see(tk.END)
                elif message_type == "error":
                    if self.llm_response_output.get("1.0", tk.END).strip() == "Обработка...":
                         self.llm_response_output.delete("1.0", tk.END) # Убираем "Обработка..."
                    self.llm_response_output.insert(tk.END, f"ОШИБКА: {data}\n")
                    self._update_status(f"Ошибка Ollama: {str(data)[:100]}...")
                self.llm_response_output.config(state=tk.DISABLED)
        except queue.Empty: pass
        finally:
            self.root.after(100, self._process_ollama_queue)

    def _apply_llm_response_to_editor(self):
        if not self.current_target_file_path:
            messagebox.showwarning("Нет файла", "Сначала выберите файл в редакторе.", parent=self.root)
            return
        llm_output = self.llm_response_output.get("1.0", tk.END).strip()
        if not llm_output or llm_output == "Обработка...":
            messagebox.showinfo("Нет ответа", "Нет ответа от LLM для применения.", parent=self.root)
            return
        confirm = messagebox.askyesno("Применить изменения?", 
                                      "Это заменит текущее содержимое редактора ответом от LLM. Продолжить?",
                                      parent=self.root)
        if confirm:
            self.code_editor.delete("1.0", tk.END)
            self.code_editor.insert("1.0", llm_output)
            self._update_status("Изменения от LLM применены. Не забудьте сохранить файл.")

if __name__ == '__main__':
    root = tk.Tk()
    app = OllamaCodeAssistant(root)
    root.mainloop()
