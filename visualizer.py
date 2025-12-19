import plotly.graph_objects as go

import json
import os
import glob
import hashlib

from folder_info import FolderInfo
from info import DATA_DIR


MIN_SIZE_PERCENT = 0.075  # Минимальный размер папки в процентах от общего размера диска для отображения

COLORS_PALETTE = [
    '#2E91E5', '#E15F99', '#1CA71C', '#FB0D0D', '#DA16FF', "#467979", '#B68100',
    '#750D86', '#EB663B', '#511CFB', '#00A08B', '#FB9902', '#F02720', '#BA43B4',
    '#CD202D', '#2752B6', '#9467BD', '#8C564B', '#E377C2', '#7F7F7F', '#BCBD22',
    '#17BECF', '#AEC7E8', '#FFBB78'
]


def get_color_by_name(name: str) -> str:
    """Генерирует цвет на основе имени папки (хеширование)"""
    if name == "...мелочь...":
        return "#DDDDDD" # Светло-серый для прочего
    
    idx = hashlib.sha256(name.encode('utf-8')).digest()[0] % len(COLORS_PALETTE)
    return COLORS_PALETTE[idx]


def format_bytes(size: float) -> str:
    if size == 0: return "0 B"
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels.get(n, 'PB')}"


def load_json_data(filepath: str) -> dict[str, FolderInfo]:
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def process_data_for_treemap(data: dict[str, FolderInfo]) -> \
    tuple[list[str], list[str], list[str], list[float], list[str], list[str]]:

    ids: list[str] = []
    labels: list[str] = []
    parents: list[str] = []
    values: list[float] = []
    node_colors: list[str] = [] # Список конкретных цветов для каждого блока
    hover_texts: list[str] = []

    # 1. Поиск корня
    all_subfolders: set[str] = set()
    for info in data.values():
        for sub in info.get('subfolders', []):
            all_subfolders.add(sub)
    
    root_path = None
    for path in data:
        if path not in all_subfolders:
            root_path = path
            break
            
    if not root_path and data:
        raise ValueError("Не удалось определить корневой путь в данных.")

    if not root_path: return [], [], [], [], [], []

    total_disk_size = data[root_path]['used_size']
    threshold_size = total_disk_size * (MIN_SIZE_PERCENT / 100.0)

    # Карта: Путь -> Родитель
    path_to_parent: dict[str, str] = {}
    for p, info in data.items():
        for sub in info.get('subfolders', []):
            if sub in data:
                path_to_parent[sub] = p

    valid_paths: set[str] = set()
    
    # Фильтрация
    for path, info in data.items():
        if path == root_path or info['used_size'] >= threshold_size:
            valid_paths.add(path)

    others_accumulator: dict[str, float] = {} 

    # Сортируем ключи, чтобы цвета не "прыгали" при разных запусках
    sorted_paths = sorted(data.keys())

    for path in sorted_paths:
        info = data[path]
        size = info['used_size']
        parent = path_to_parent.get(path, "")

        if path in valid_paths:
            folder_name = os.path.basename(path.rstrip(os.sep)) or path
            
            ids.append(path)
            labels.append(folder_name)
            parents.append(parent)
            values.append(size)
            
            # Генерируем цвет на основе имени папки
            node_colors.append(get_color_by_name(folder_name))
            
            percent = (size / total_disk_size) * 100
            hover_texts.append(f"<b>{folder_name}</b><br>{format_bytes(size)}<br>({percent:.1f}% от всего диска)")
        
        else:
            if parent and parent in valid_paths:
                others_accumulator[parent] = others_accumulator.get(parent, 0) + size

    # Добавляем узлы "Прочее"
    for parent_path, others_size in others_accumulator.items():
        if others_size > 0:
            other_id = f"{parent_path}/__others__"
            ids.append(other_id)
            labels.append("...мелочь...")
            parents.append(parent_path)
            values.append(others_size)
            node_colors.append(get_color_by_name("...мелочь..."))
            hover_texts.append(f"Мелкие файлы (<{MIN_SIZE_PERCENT}%)<br>Суммарно: {format_bytes(others_size)}")

    return ids, labels, parents, values, node_colors, hover_texts


def create_treemap(json_filepath: str) -> None:
    data = load_json_data(json_filepath)
    if not data: return

    print(f"Обработка {json_filepath}...")
    ids, labels, parents, values, node_colors, hover_texts = process_data_for_treemap(data)
    
    if not ids:
        print("Нет данных для отображения")
        return

    filename = os.path.basename(json_filepath)
    
    fig = go.Figure(go.Treemap(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        textinfo="label+text+percent parent",
        hoverinfo="text",
        hovertext=hover_texts,
        marker=dict(
            colors=node_colors, # Используем наш список цветов
            # colorscale больше не нужен, так как мы задаем цвета напрямую
        ),
        pathbar=dict(visible=True),
        tiling=dict(pad=2) # Небольшой отступ между квадратами для красоты
    ))

    fig.update_layout( # type: ignore
        title=f"Диск: {filename} | Всего: {format_bytes(values[0])}",
        margin=dict(t=60, l=0, r=0, b=0),
        height=800,
        font=dict(family="Verdana", size=14)
    )

    output_file = json_filepath.replace('.json', '.html')
    fig.write_html(output_file) # type: ignore
    print(f"Готово -> {output_file}")


def main():
    json_files = glob.glob("*.json", root_dir=DATA_DIR)
    if not json_files:
        print("JSON файлы не найдены.")
        return

    for f in json_files:
        try:
            create_treemap(os.path.join(DATA_DIR, f))
        except Exception as e:
            print(f"Ошибка {f}: {e}")


if __name__ == "__main__":
    main()