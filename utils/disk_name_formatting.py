def format_disk_name(name: str) -> str:
    return name.replace(':', '').replace('/', '_').replace('\\', '_').strip('_')
