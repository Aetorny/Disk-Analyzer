from typing import Any
from math import log10
import plotly.graph_objects as go
import json
import os
import glob

from pathlib import Path
from info import DATA_DIR


# Порог группировки:
# 1) если файл/папка занимает меньше 1% от РОДИТЕЛЯ, он уходит в "Прочее"
# 2) если он занимает меньше 75 МБ от общего объема диска, он уходит в "Прочее"
SMALL_FILE_THRESHOLD_RATIO = 0.01
ABSOLUTE_MIN_SIZE = 75 * 1024 * 1024 

# Настройка цветов (Heatmap)
COLOR_SCALE = 'Turbo'


def format_bytes(size: float) -> str:
    if size == 0: return "0 B"
    power = 2**10
    n = 0
    power_labels = {0 : 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB', 5: 'PB'}
    while size >= power and n < 5:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def load_json_data(filepath: Path) -> dict[str, Any]:
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_hierarchy(data: dict[str, dict[str, Any]]) -> tuple[dict[str, list[tuple[Path, dict[str, Any]]]], Path]:
    """
    Преобразует плоский словарь из JSON в структуру:
    parent_path -> list of items (path, info)
    """
    hierarchy: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    
    # Сначала найдем корень (путь, которого нет ни у кого в subfolders)
    all_subfolders: set[str] = set()
    for info in data.values():
        for sub in info.get('subfolders', []):
            all_subfolders.add(str(Path(sub))) # Нормализуем пути через Path
    
    root_path = None
    # Ищем ключ, который не является ничьим subfolder
    for path_str in data:
        p_obj = Path(path_str)
        if str(p_obj) not in all_subfolders:
            root_path = p_obj
            break
            
    if not root_path:
        # Fallback: если корень не найден, берем самый короткий путь
        root_path = Path(min(data.keys(), key=len))

    # Строим карту родитель -> дети
    for path_str, info in data.items():
        # Приводим все пути к объектам Path для надежности
        path = Path(path_str)
        
        # Для каждого пути найдем его детей в исходных данных
        subfolders = info.get('subfolders', [])
        
        children: list[tuple[Path, dict[str, Any]]] = []
        for sub_str in subfolders:
            sub_path = Path(sub_str)
            if str(sub_str) in data: # Проверяем, есть ли данные по ребенку
                children.append((sub_path, data[str(sub_str)]))
            else:
                # Если данных нет (файл в корне без своей записи), можно добавить фиктивно, 
                # но обычно сканеры пишут все файлы.
                pass
        
        hierarchy[str(path)] = children

    return hierarchy, root_path


def process_data_for_treemap(data: dict[str, dict[str, Any]]) -> tuple[
    list[str], list[str], list[str], list[float], list[str], list[str]
    ]:
    hierarchy, root_path = build_hierarchy(data)
    
    ids: list[str] = []
    labels: list[str] = []
    parents: list[str] = []
    values: list[float] = []
    hover_texts: list[str] = []
    custom_data: list[str] = [] # Для передачи путей в JS

    # Стек для обхода: (path, parent_id)
    # Используем str для ID, чтобы Plotly не ругался
    
    root_str = str(root_path)
    root_used = data[root_str]['used_size']
    
    ids.append(root_str)
    labels.append(root_path.name or str(root_path))
    parents.append("")
    values.append(root_used)
    hover_texts.append(f"Root: {format_bytes(root_used)}")
    custom_data.append(root_str)

    # Очередь для обработки: (current_path_obj)
    queue = [root_path]

    while queue:
        curr_path = queue.pop(0)
        curr_str = str(curr_path)
        
        # Получаем детей из иерархии
        children = hierarchy.get(curr_str, [])
        if not children:
            continue

        # Получаем размер текущей папки для расчета %
        parent_size = data[curr_str]['used_size']
        if parent_size == 0: continue

        others_size = 0
        others_count = 0
        
        # Сортируем детей, чтобы порядок был детерминирован
        children.sort(key=lambda x: x[1]['used_size'], reverse=True)

        for child_path, child_info in children:
            child_size = child_info['used_size']
            child_str = str(child_path)

            if child_size < (parent_size * SMALL_FILE_THRESHOLD_RATIO) or child_size < ABSOLUTE_MIN_SIZE:
                others_size += child_size
                others_count += 1
                continue

            # Добавляем нормальный узел
            ids.append(child_str)
            labels.append(child_path.name)
            parents.append(curr_str)
            values.append(child_size)
            custom_data.append(child_str) # Полный путь для копирования
            
            # Тултип
            pct_parent = (child_size / parent_size) * 100
            pct_disk = (child_size / root_used) * 100
            disk_info = f"<br>{pct_disk:.2f}% от занятого"

            hover_texts.append(
                f"<b>{child_path.name}</b><br>"
                f"{format_bytes(child_size)}<br>"
                f"{pct_parent:.1f}% от родителя"
                f"{disk_info}"
            )

            # Добавляем в очередь для обработки его детей
            if child_str in hierarchy:
                queue.append(child_path)

        # Добавляем узел "Прочее", если накопилось
        if others_size > 0:
            other_id = f"{curr_str}/__others__"
            ids.append(other_id)
            labels.append(f"...небольшие файлы ({others_count})...")
            parents.append(curr_str)
            values.append(others_size)
            custom_data.append(f"Группа мелких файлов в {curr_path.name}")
            
            pct_parent = (others_size / parent_size) * 100
            hover_texts.append(
                f"Мелкие файлы (<{SMALL_FILE_THRESHOLD_RATIO*100}% от папки)<br>"
                f"Суммарно: {format_bytes(others_size)}<br>"
                f"{pct_parent:.1f}% от {curr_path.name}"
            )

    return ids, labels, parents, values, hover_texts, custom_data


def create_treemap(json_filepath: str) -> None:
    path_obj = Path(json_filepath)
    print(f"Обработка {path_obj.name}...")
    
    data = load_json_data(path_obj)
    if not data: return

    ids, labels, parents, values, hover_texts, custom_data = process_data_for_treemap(data)
    
    if not ids:
        print("Нет данных.")
        return

    min_log = log10(ABSOLUTE_MIN_SIZE) if ABSOLUTE_MIN_SIZE > 0 else 0
    
    max_val = max(values) if values else 1
    max_log = log10(max_val)

    # Название графика
    title_text = f"Диск: {path_obj.name} | " + \
        f"Занято: {format_bytes(data[str(min(data.keys(), key=len))]['used_size'])}"

    fig = go.Figure(go.Treemap(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        textinfo="label+text+percent parent",
        hoverinfo="text",
        hovertext=hover_texts,
        customdata=custom_data, # Данные для JS клика
        pathbar=dict(visible=True, thickness=25),
        
        # HEATMAP: Цвет зависит от Values (размера папок)
        marker=dict(
            colors=[log10(v) if v > 0 else 0 for v in values],
            colorscale=COLOR_SCALE,
            cmin=min_log,
            cmax=max_log,
            showscale=True,
            colorbar=dict(
                title="Размер",
                tickvals=[i for i in range(int(min_log), int(max_log) + 2)],
                ticktext=[format_bytes(10**i) for i in range(int(min_log), int(max_log) + 2)]
            ),
            line=dict(
                width=1,         # Ширина границы в пикселях (1 или 2 обычно достаточно)
                color='#FFFFFF'  # Цвет границы (Белый для яркости, или '#333333' для темной темы)
            ),
        ),
        tiling=dict(pad=3),
    ))

    fig.update_layout( # type: ignore
        title=title_text,
        margin=dict(t=50, l=10, r=10, b=10),
        height=900,
        font=dict(family="Verdana", size=14),
        hoverlabel=dict(bgcolor="white", font_size=14)
    )

    output_file = path_obj.with_suffix('.html')
    
    # Генерируем HTML
    html_content = fig.to_html(include_plotlyjs='cdn', full_html=True) # type: ignore
    
    # --- JS INJECTION: Кастомное контекстное меню ---
    js_script = """
        <style>
            /* Стиль контекстного меню */
            #custom-context-menu {
                display: none;
                position: absolute;
                z-index: 10000;
                background-color: #ffffff;
                border: 1px solid #ccc;
                box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
                border-radius: 4px;
                font-family: Verdana, sans-serif;
                font-size: 14px;
                padding: 5px 0;
                min-width: 150px;
            }
            
            .ctx-item {
                padding: 8px 15px;
                cursor: pointer;
                color: #333;
                transition: background 0.1s;
            }
            
            .ctx-item:hover {
                background-color: #f0f0f0;
            }
            
            .ctx-separator {
                border-bottom: 1px solid #eee;
                margin: 4px 0;
            }
        </style>

        <!-- Само меню -->
        <div id="custom-context-menu">
            <div class="ctx-item" id="btn-copy-path">📂 Скопировать путь</div>
            <div class="ctx-item" id="btn-copy-name">📄 Скопировать имя</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item" style="color: #888;" id="btn-cancel">Отмена</div>
        </div>

        <script>
        document.addEventListener("DOMContentLoaded", function(){
            var plotElement = document.getElementsByClassName('plotly-graph-div')[0];
            var menu = document.getElementById('custom-context-menu');
            var btnCopyPath = document.getElementById('btn-copy-path');
            var btnCopyName = document.getElementById('btn-copy-name');
            var btnCancel = document.getElementById('btn-cancel');
            
            // Храним данные элемента под курсором
            var currentHoveredPath = null;
            var currentHoveredLabel = null;

            // 1. Отслеживаем, на чем сейчас мышь (Plotly Hover)
            plotElement.on('plotly_hover', function(data){
                if(data.points.length > 0){
                    currentHoveredPath = data.points[0].customdata;
                    currentHoveredLabel = data.points[0].label;
                }
            });

            // 2. Ловим Правый Клик на графике
            plotElement.addEventListener('contextmenu', function(e) {
                e.preventDefault(); // Блокируем стандартное меню браузера
                
                if (currentHoveredPath) {
                    // Показываем меню в координатах мыши
                    menu.style.display = 'block';
                    menu.style.left = e.pageX + 'px';
                    menu.style.top = e.pageY + 'px';
                }
            });

            // 3. Логика кнопок
            btnCopyPath.onclick = function() {
                if (currentHoveredPath) {
                    navigator.clipboard.writeText(currentHoveredPath).then(function() {
                        console.log('Path copied: ' + currentHoveredPath);
                        menu.style.display = 'none';
                    });
                }
            };
            
            btnCopyName.onclick = function() {
                if (currentHoveredLabel) {
                    navigator.clipboard.writeText(currentHoveredLabel).then(function() {
                        console.log('Name copied: ' + currentHoveredLabel);
                        menu.style.display = 'none';
                    });
                }
            };
            
            btnCancel.onclick = function() {
                menu.style.display = 'none';
            };

            // 4. Скрытие меню при клике в любом другом месте
            document.addEventListener('click', function(e) {
                if (e.target.closest('#custom-context-menu') === null) {
                    menu.style.display = 'none';
                }
            });
            
            // Скрытие при скролле (чтобы меню не уехало)
            document.addEventListener('scroll', function() {
                menu.style.display = 'none';
            });
        });
        </script>
        """
    
    # Вставляем скрипт перед закрывающим body
    html_content = html_content.replace('</body>', f'{js_script}</body>')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Готово -> {output_file}")


def main() -> None:
    json_files = glob.glob("*.json", root_dir=DATA_DIR)
    if not json_files:
        print("JSON файлы не найдены.")
        return

    for f in json_files:
        try:
            full_path = os.path.join(DATA_DIR, f)
            create_treemap(full_path)
        except Exception as e:
            print(f"Ошибка {f}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()