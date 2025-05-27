import re
import os
import sys
import shutil
from datetime import datetime
import tokenize # Import the tokenize module

# --- Вспомогательные функции для очистки ---

def _clean_python_code(content, compact_mode=False):
    """
    Удаляет комментарии и docstrings из Python кода.
    В зависимости от compact_mode, либо оставляет отступы и пустые строки, либо максимально сжимает.
    """
    cleaned_lines = []
    
    try:
        # Using io.StringIO to treat the string content as a file for tokenize
        from io import StringIO
        f = StringIO(content)

        last_token_end_col = 0
        last_token_end_row = 1 # Lines are 1-indexed

        for toktype, tokstr, (srow, scol), (erow, ecol), line_text in tokenize.generate_tokens(f.readline):
            # Skip comments
            if toktype == tokenize.COMMENT:
                continue 

            # Skip potential docstrings if they are the only thing on the line
            if toktype == tokenize.STRING and (tokstr.startswith('"""') or tokstr.startswith("'''")):
                # Heuristic: if the stripped line content is just this string, skip it
                if line_text.strip() == tokstr.strip():
                    continue

            # In compact mode, we don't care about preserving original spacing,
            # we'll just add tokens back tightly.
            if compact_mode:
                if toktype == tokenize.NEWLINE:
                    if reconstructed_content and reconstructed_content[-1] != '\n':
                        cleaned_lines.append('\n')
                elif toktype not in [tokenize.INDENT, tokenize.DEDENT]: # Indents/dedents are handled by reconstruction
                    cleaned_lines.append(tokstr)
            else: # Readable mode: try to preserve original layout
                # Add newlines for line breaks
                if srow > last_token_end_row:
                    cleaned_lines.append('\n' * (srow - last_token_end_row))
                    last_token_end_col = 0 # Reset column for new line

                # Add spaces for indentation or gaps between tokens
                if scol > last_token_end_col:
                    cleaned_lines.append(' ' * (scol - last_token_end_col))
                
                cleaned_lines.append(tokstr)
            
            last_token_end_row = erow
            last_token_end_col = ecol

        cleaned_content_str = "".join(cleaned_lines)

    except tokenize.TokenError as e:
        print(f"Предупреждение: Ошибка токенизации Python файла. Возможно, синтаксическая ошибка. {e}")
        # Fallback to regex for this specific problematic file if tokenize fails critically
        return _clean_python_code_fallback_regex(content, compact_mode)
    except Exception as e:
        print(f"Предупреждение: Непредвиденная ошибка при токенизации Python файла. {e}")
        return _clean_python_code_fallback_regex(content, compact_mode)

    # Final cleanup regardless of mode
    if compact_mode:
        cleaned_content_str = re.sub(r'\n+', '\n', cleaned_content_str).strip() # Remove all extra newlines
        cleaned_content_str = re.sub(r'[ \t]+', '', cleaned_content_str) # Remove all whitespace
    else: # Readable mode
        cleaned_content_str = re.sub(r'\n{3,}', '\n\n', cleaned_content_str) # Max two newlines
        cleaned_content_str = re.sub(r'[ \t]+$', '', cleaned_content_str, flags=re.MULTILINE) # Remove trailing whitespace
        cleaned_content_str = cleaned_content_str.strip() # Remove leading/trailing blank lines in file
        
    return cleaned_content_str

def _clean_python_code_fallback_regex(content, compact_mode=False):
    """Fallback for Python using regex (less reliable but won't crash on some token errors)."""
    lines = content.splitlines()
    cleaned_lines = []
    in_multiline_string = False

    for line in lines:
        original_line_stripped = line.strip()

        # Simple check for multiline strings
        triple_quote_patterns = ['"""', "'''"]
        for pattern in triple_quote_patterns:
            if original_line_stripped.startswith(pattern):
                if original_line_stripped.count(pattern) % 2 == 1:
                    in_multiline_string = not in_multiline_string
                break
        
        if in_multiline_string:
            continue # Skip lines inside multiline strings (as if they were docstrings)

        if original_line_stripped.startswith('#'):
            continue # Remove lines that are entirely # comments

        # Remove inline comments
        match = re.search(r'#', line)
        if match:
            pre_comment_part = line[:match.start()]
            single_quotes_odd = (pre_comment_part.count("'") - pre_comment_part.count("\\'")) % 2 == 1
            double_quotes_odd = (pre_comment_part.count('"') - pre_comment_part.count('\\"')) % 2 == 1
            
            if single_quotes_odd or double_quotes_odd:
                cleaned_lines.append(line) # # is likely inside a string
            else:
                cleaned_lines.append(line[:match.start()].rstrip())
        else:
            cleaned_lines.append(line)
    
    cleaned_content_str = "\n".join(cleaned_lines)
    # Remove all triple-quoted strings after initial pass
    cleaned_content_str = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', '', cleaned_content_str)

    if compact_mode:
        cleaned_content_str = re.sub(r'\s+', '', cleaned_content_str).strip() # Remove all whitespace
    else:
        cleaned_content_str = re.sub(r'\n{3,}', '\n\n', cleaned_content_str)
        cleaned_content_str = re.sub(r'[ \t]+$', '', cleaned_content_str, flags=re.MULTILINE)
        cleaned_content_str = cleaned_content_str.strip()
    return cleaned_content_str


def _clean_html_js_css_code(content, compact_mode=False):
    """
    Удаляет комментарии из HTML, JS или CSS кода.
    В зависимости от compact_mode, либо оставляет отступы и пустые строки, либо максимально сжимает.
    """
    # Remove multi-line comments first
    cleaned_content_str = re.sub(r'', '', content) # HTML
    cleaned_content_str = re.sub(r'/\*[\s\S]*?\*/', '', cleaned_content_str) # JS/CSS

    processed_lines = []
    for line in cleaned_content_str.splitlines():
        original_line_stripped = line.strip()

        if original_line_stripped.startswith('//'):
            continue # Remove lines that are entirely // comments

        match = re.search(r'//', line)
        if match:
            pre_comment_part = line[:match.start()]
            single_quotes_odd = (pre_comment_part.count("'") - pre_comment_part.count("\\'")) % 2 == 1
            double_quotes_odd = (pre_comment_part.count('"') - pre_comment_part.count('\\"')) % 2 == 1
            
            if single_quotes_odd or double_quotes_odd:
                processed_lines.append(line) # // is likely inside a string, keep
            else:
                processed_lines.append(line[:match.start()].rstrip()) # Remove comment
        else:
            processed_lines.append(line)
    
    cleaned_content_str = "\n".join(processed_lines)

    # Final cleanup based on mode
    if compact_mode:
        cleaned_content_str = re.sub(r'\s+', '', cleaned_content_str).strip() # Remove all whitespace
    else:
        cleaned_content_str = re.sub(r'\n{3,}', '\n\n', cleaned_content_str) # Max two newlines
        cleaned_content_str = re.sub(r'[ \t]+$', '', cleaned_content_str, flags=re.MULTILINE) # Remove trailing whitespace
        cleaned_content_str = cleaned_content_str.strip() # Remove leading/trailing blank lines in file
        
    return cleaned_content_str


# --- Основная логика обработки файлов ---

def process_file(filepath, backup_dir, compact_mode):
    """
    Обрабатывает один файл: удаляет комментарии и делает бэкап.
    """
    filename, file_extension = os.path.splitext(filepath)
    file_extension = file_extension.lower()

    supported_extensions = ['.py', '.html', '.js', '.css']
    if file_extension not in supported_extensions:
        return 

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()

        cleaned_content = original_content

        if file_extension == '.py':
            cleaned_content = _clean_python_code(original_content, compact_mode)
        elif file_extension in ['.html', '.js', '.css']:
            cleaned_content = _clean_html_js_css_code(original_content, compact_mode)
        
        if cleaned_content != original_content:
            # Create backup
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            relative_path = os.path.relpath(filepath, start=script_dir)
            backup_filepath = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(backup_filepath), exist_ok=True)
            shutil.copy2(filepath, backup_filepath)
            print(f"Бэкап создан: {backup_filepath}")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            print(f"Очищено: {filepath} (Режим: {'Плотный' if compact_mode else 'Читаемый'})")
        # else:
        #     print(f"В файле '{filepath}' не найдено комментариев или изменений.")

    except Exception as e:
        print(f"Ошибка при обработке '{filepath}': {e}")


def main():
    current_directory = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder_name = f"backup_cleaned_files_{timestamp}"
    backup_dir = os.path.join(current_directory, backup_folder_name)
    
    os.makedirs(backup_dir, exist_ok=True)
    print(f"Файлы будут бэкапированы в: {backup_dir}")

    print("\nВыберите режим очистки:")
    print("1. Читаемый (Readable): Сохраняет отступы и разумные пустые строки для удобства чтения человеком (рекомендуется для проектов).")
    print("2. Плотный (Compact): Удаляет все пустые строки и лишние пробелы для максимальной компактности (удобно для нейросетей).")
    
    mode_choice = input("Введите 1 или 2: ").strip()
    
    compact_mode = False
    if mode_choice == '2':
        compact_mode = True
        print("Выбран плотный режим.")
    elif mode_choice == '1':
        print("Выбран читаемый режим.")
    else:
        print("Неверный выбор. По умолчанию будет использоваться читаемый режим.")

    print(f"\nНачинаем очистку от комментариев в: {current_directory} и всех подпапках...")

    ignored_dirs = ['venv', '.venv']

    for root, dirs, files in os.walk(current_directory):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]

        for file in files:
            filepath = os.path.join(root, file)
            if os.path.abspath(filepath) == os.path.abspath(sys.argv[0]) or filepath.startswith(backup_dir):
                continue
            
            process_file(filepath, backup_dir, compact_mode)
    
    print("\nОчистка завершена!")
    print(f"Резервные копии всех измененных файлов находятся в папке: {backup_dir}")

if __name__ == "__main__":
    print("--- ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ ---")
    print("Этот скрипт изменяет файлы напрямую.")
    print("Автоматически будут созданы резервные копии измененных файлов в новой папке.")
    print("Всегда рекомендуется иметь дополнительные резервные копии ваших проектов!")
    input("Нажмите Enter, чтобы продолжить, или закройте окно, чтобы отменить...")

    main()
