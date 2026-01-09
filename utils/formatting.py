from datetime import datetime


def format_bytes(size: float) -> str:
    if size == 0: return "0 B"
    power = 2**10
    n = 0
    power_labels = {0 : 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB', 5: 'PB'}
    while size >= power and n < 5:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def format_path(path: str) -> str:
    return path.replace(':', '').replace('/', '_').replace('\\', '_').strip('_')


def _plural(n: int, forms: list[str]) -> str:
    '''
    Возвращает верную форму слова в зависимости от количества
    '''
    return forms[0] if n % 10 == 1 and n % 100 != 11 else \
           forms[1] if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else \
           forms[2]

def format_date_to_time_ago(date_str: str) -> str:
    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    delta = now - date

    seconds = int(delta.total_seconds())
    minutes = seconds // 60
    hours = minutes // 60
    days = delta.days

    if days > 0:
        return f"{days} {_plural(days, ['день', 'дня', 'дней'])} назад"
    if hours > 0:
        return f"{hours} {_plural(hours, ['час', 'часа', 'часов'])} назад"
    if minutes > 0:
        return f"{minutes} {_plural(minutes, ['минута', 'минуты', 'минут'])} назад"
    return "только что"
