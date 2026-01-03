def format_bytes(size: float) -> str:
    if size == 0: return "0 B"
    power = 2**10
    n = 0
    power_labels = {0 : 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB', 5: 'PB'}
    while size >= power and n < 5:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"
