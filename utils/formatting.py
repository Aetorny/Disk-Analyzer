from datetime import datetime
from config import TRANSLATOR


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


def format_date_to_time_ago(date_str: str) -> str:
    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    delta = now - date

    seconds = int(delta.total_seconds())
    minutes = seconds // 60
    hours = minutes // 60
    days = delta.days

    if days > 0:
        msg = TRANSLATOR.ngettext('formatting')("{n} day ago", "{n} days ago", days)
        return msg.format(n=days)

    if hours > 0:
        msg = TRANSLATOR.ngettext('formatting')("{n} hour ago", "{n} hours ago", hours)
        return msg.format(n=hours)

    if minutes > 0:
        msg = TRANSLATOR.ngettext('formatting')("{n} minute ago", "{n} minutes ago", minutes)
        return msg.format(n=minutes)

    return TRANSLATOR.gettext('formatting')("just now")
