def choose_disk(disks: list[str]) -> list[str]:
    excluded_disks: list[str] = []
    while True:
        print('Сейчас будут сканироваться следующие диски:')
        for i, disk in enumerate(disks):
            print('\t[X]' if disk not in excluded_disks else '\t[ ]', end=' ')
            print(f'{i + 1}: {disk}')
        n_str = input('Выберите какой диск хотите отключить/включить (номер) или нажмите enter для начала сканирования: ')
        if n_str.isnumeric():
            n = int(n_str)
            if n >= 1 or n <= len(disks):
                disk = disks[n - 1]
                if disk in excluded_disks:
                    excluded_disks.remove(disk)
                else:
                    excluded_disks.append(disks[n - 1])
                continue
        elif n_str == '':
            break
        print('---\nНеверный номер диска\n---')
    return [disk for disk in disks if disk not in excluded_disks]
