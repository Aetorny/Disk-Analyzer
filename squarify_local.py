def normalize_sizes(sizes: list[float], dx: float, dy: float, total_size: float) -> list[float]:
    """
    Нормализует список числовых значений так, чтобы `sum(sizes) == dx * dy`.
    """
    total_size = total_size
    total_area = dx * dy
    return list([size * total_area / total_size for size in sizes])

def squarify(sizes: list[float], x: float, y: float, dx: float, dy: float) -> list[dict[str, float]]:
    """
    Разбивает список числовых значений на квадраты
    sizes обязан быть отсортирован по убыванию
    """
    
    if not sizes:
        return []

    rects: list[dict[str, float]] = []

    # Текущая позиция и размеры canvas
    curr_x, curr_y = x, y
    curr_dx, curr_dy = dx, dy

    row_sum = 0.0
    row_vals: list[float] = []

    def layout_row(r_vals: list[float], r_sum: float, cx: float, cy: float, cdx: float, cdy: float) -> tuple[float, float, float, float]:
        """Отрисовывает ряд и возвращает оставшееся пространство"""
        
        nonlocal rects
        
        is_horizontal = cdx >= cdy
        
        side = cdy if is_horizontal else cdx
        
        thickness = r_sum / side
        
        ref_x, ref_y = cx, cy
        
        for val in r_vals:
            if is_horizontal:
                h = val / thickness
                rects.append({"x": ref_x, "y": ref_y, "dx": thickness, "dy": h})
                ref_y += h
            else:
                w = val / thickness
                rects.append({"x": ref_x, "y": ref_y, "dx": w, "dy": thickness})
                ref_x += w
                
        if is_horizontal:
            return cx + thickness, cy, cdx - thickness, cdy
        else:
            return cx, cy + thickness, cdx, cdy - thickness

    def worst_ratio(r_sum: float, r_min: float, r_max: float, w: float) -> float:
        """
        Вычисляет худшее соотношение сторон для ряда с заданной суммой,
        мин/макс элементом и длиной стороны w.
        """
        if r_sum == 0 or w == 0: return 0
        s2 = r_sum * r_sum
        w2 = w * w
        return max((w2 * r_max) / s2, s2 / (w2 * r_min))

    idx = 0
    while idx < len(sizes):
        val = sizes[idx]
        
        w = min(curr_dx, curr_dy)
        
        if not row_vals:
            row_vals.append(val)
            row_sum = val
            idx += 1
        else:
            new_sum = row_sum + val
            curr_min = row_vals[-1]
            curr_max = row_vals[0]
            
            new_min = val
            new_max = row_vals[0]
            
            curr_worst = worst_ratio(row_sum, curr_min, curr_max, w)
            new_worst = worst_ratio(new_sum, new_min, new_max, w)
            
            if curr_worst >= new_worst:
                row_vals.append(val)
                row_sum += val
                idx += 1
            else:
                curr_x, curr_y, curr_dx, curr_dy = layout_row(
                    row_vals, row_sum, curr_x, curr_y, curr_dx, curr_dy
                )
                row_vals = []
                row_sum = 0.0

    if row_vals:
        layout_row(row_vals, row_sum, curr_x, curr_y, curr_dx, curr_dy)

    return rects