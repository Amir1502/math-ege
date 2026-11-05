"""Original, unreviewed course models for profile slots 10–13.

Only the eight explicitly flagged families are public runtime templates. All
families support the central builder's seed 0..9 candidate-bank materialization.
Arithmetic is rational; float conversion is confined to visual coordinates.
"""

from fractions import Fraction
from typing import Any

from app.generators.base import Family, decimal_text, make_task
from app.schemas import ProfileSource


def _digits(seed: int, *radices: int) -> tuple[int, ...]:
    """Bounded mixed-radix parameters, independent of Python's random version."""
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    values = []
    for radix in radices:
        values.append(seed % radix)
        seed //= radix
    return tuple(values)


def _table(*rows: tuple[str, Fraction | int, str]) -> dict[str, Any]:
    return {
        "headers": ["Величина", "Значение", "Единица"],
        "rows": [[name, decimal_text(value), unit] for name, value, unit in rows],
    }


def _coordinate(value: Fraction | int) -> int | float:
    rational = Fraction(value)
    return rational.numerator if rational.denominator == 1 else float(rational)


def _point(x: Fraction | int, y: Fraction | int) -> dict[str, int | float]:
    return {"x": _coordinate(x), "y": _coordinate(y)}


def _figure(
    description: str,
    lines: list[list[tuple[Fraction | int, Fraction | int]]],
    marks: list[tuple[str, Fraction | int, Fraction | int]],
) -> dict[str, Any]:
    points = [pair for line in lines for pair in line] + [(x, y) for _, x, y in marks]
    xs, ys = [0, *(p[0] for p in points)], [0, *(p[1] for p in points)]
    return {
        "description": description,
        "x_min": _coordinate(min(xs) - 2), "x_max": _coordinate(max(xs) + 2),
        "y_min": _coordinate(min(ys) - 2), "y_max": _coordinate(max(ys) + 2),
        "axes": True,
        "lines": [{"points": [_point(x, y) for x, y in line]} for line in lines],
        "circles": [{"center": _point(x, y), "radius": 0.12} for _, x, y in marks],
        "labels": [{**_point(x + Fraction(1, 4), y + Fraction(1, 2)), "text": name}
                   for name, x, y in marks],
    }


def _task(profile: ProfileSource, seed: int, family_id: str, **values: Any) -> dict:
    family = _BY_ID[family_id]
    answer = values["answer"]
    values["solution"] = [*values["solution"], f"Ответ: {decimal_text(answer)}."]
    return make_task(
        profile, family.slot, family.id, seed, title=family.title,
        skills=list(family.skill_ids), **values,
    )


def _heat(seed: int, profile: ProfileSource) -> dict:
    k, start, rise = _digits(seed, 23, 15, 15)
    grams, initial, final = 1000 + 100 * k, 10 + start, 40 + start + rise
    mass = Fraction(grams, 1000)
    energy = 4200 * mass * (final - initial)
    return _task(
        profile, seed, "heat-balance",
        statement=("Воду нагревают без потерь теплоты и без изменения агрегатного состояния. "
                   "Удельную теплоёмкость считайте постоянной. Данные приведены в таблице. "
                   "По формуле Q = cm(T₂ − T₁) найдите полученную теплоту в килоджоулях."),
        formula=r"Q = c m (T_2-T_1)", answer=energy / 1000,
        table=_table(("Масса воды", grams, "г"),
                     ("Удельная теплоёмкость", 4200, "Дж/(кг·°C)"),
                     ("Начальная температура", initial, "°C"),
                     ("Конечная температура", final, "°C")),
        hints=["Сначала согласуйте единицу массы с единицами теплоёмкости.",
               "Переведите граммы в килограммы и используйте Q = cm(T₂ − T₁).",
               f"Масса равна {decimal_text(mass)} кг; умножьте её на 4200 и "
               f"на разность температур {final - initial} °C, затем разделите на 1000."],
        solution=[f"Масса: {grams}/1000 = {decimal_text(mass)} кг.",
                  f"Изменение температуры: {final} − {initial} = {final - initial} °C.",
                  f"Q = 4200 · {decimal_text(mass)} · {final - initial} = "
                  f"{decimal_text(energy)} Дж = {decimal_text(energy / 1000)} кДж. "
                  "Температура ниже кипения, теплота положительна."],
    )


def _pressure(seed: int, profile: ProfileSource) -> dict:
    k, area_part = _digits(seed, 23, 11)
    pressure, area = 60 + 2 * k, 50 + 5 * area_part
    force = Fraction(pressure * area, 10)
    return _task(
        profile, seed, "pressure-force",
        statement=("Плоская опора равномерно давит на поверхность. Давление p и площадь "
                   "контакта S указаны в таблице. Используя p = F/S, найдите силу F "
                   "в ньютонах. Один паскаль равен одному ньютону на квадратный метр."),
        formula=r"p = \frac{F}{S}", answer=force,
        table=_table(("Давление", pressure, "кПа"), ("Площадь", area, "см²")),
        hints=["Выразите силу и проверьте, в каких единицах должна стоять площадь.",
               "Из p = F/S следует F = pS; 1 кПа = 1000 Па, 1 см² = 0,0001 м².",
               f"Вычислите {pressure} · 1000 · ({area}/10000)."],
        solution=["Умножаем обе части p = F/S на положительную площадь: F = pS.",
                  f"p = {pressure * 1000} Па, S = {decimal_text(Fraction(area, 10000))} м².",
                  f"F = {pressure * 1000} · {decimal_text(Fraction(area, 10000))} "
                  f"= {decimal_text(force)} Н; деление на S возвращает заданное давление."],
    )


def _tank(seed: int, profile: ProfileSource) -> dict:
    k, first, second, volume = _digits(seed, 23, 5, 5, 9)
    duration, outflow, net, initial = 10 + k, 2 + first, 3 + second, 40 + 5 * volume
    inflow = outflow + net
    target, capacity = initial + net * duration, initial + net * duration + 50
    return _task(
        profile, seed, "tank-net-flow",
        statement=("В бак непрерывно поступает вода и одновременно вытекает через слив. "
                   "Оба расхода постоянны, других притоков и потерь нет. В таблице даны "
                   "начальный и требуемый объёмы, расходы и вместимость. Через сколько "
                   "минут объём впервые станет требуемым?"),
        formula=None, answer=duration,
        table=_table(("Начальный объём", initial, "л"), ("Приток", inflow, "л/мин"),
                     ("Отток", outflow, "л/мин"), ("Требуемый объём", target, "л"),
                     ("Вместимость", capacity, "л")),
        hints=["Найдите, на сколько литров увеличивается запас за одну минуту.",
               "Баланс воды: V(t) = V₀ + (qвх − qвых)t, пока бак не переполнен.",
               f"Решите уравнение {initial} + ({inflow} − {outflow})t = {target}."],
        solution=[f"Чистый приток: {inflow} − {outflow} = {net} л/мин.",
                  f"Нужно добавить {target} − {initial} = {target - initial} л. "
                  f"Время: {target - initial}/{net} = {duration} мин.",
                  f"Объём растёт от {initial} до {target} л, оба значения меньше "
                  f"{capacity} л. Опустошения и переполнения до этого момента нет."],
    )


def _resistance(seed: int, profile: ProfileSource) -> dict:
    k, level = _digits(seed, 23, 13)
    base, reference, temperature, alpha = 50 + 5 * k, 20, 30 + 5 * level, Fraction(1, 250)
    measured = base * (1 + alpha * (temperature - reference))
    return _task(
        profile, seed, "resistance-temperature",
        statement=("Для датчика в диапазоне от 0 до 100 °C действует модель "
                   "R = R₀(1 + α(T − T₀)). В таблице указаны опорное сопротивление R₀ "
                   "при температуре T₀, коэффициент α и измеренное сопротивление R. "
                   "Определите температуру T в градусах Цельсия."),
        formula=r"R=R_0\bigl(1+\alpha(T-T_0)\bigr)", answer=temperature,
        table=_table(("Опорное сопротивление", base, "Ом"),
                     ("Опорная температура", reference, "°C"),
                     ("Коэффициент", alpha, "1/°C"),
                     ("Измеренное сопротивление", measured, "Ом")),
        hints=["В скобках скрыто изменение температуры, а не сама температура.",
               "Разделите на R₀, вычтите единицу, затем разделите на α и прибавьте T₀.",
               f"Вычислите 20 + ({decimal_text(measured)}/{base} − 1)/0,004."],
        solution=[f"R/R₀ − 1 = {decimal_text(measured)}/{base} − 1 = "
                  f"{decimal_text(alpha * (temperature - reference))}.",
                  f"T − 20 = {decimal_text(alpha * (temperature - reference))}/0,004 "
                  f"= {temperature - reference}; T = {temperature} °C.",
                  f"Полученное значение лежит в диапазоне 0–100 °C. При подстановке "
                  f"R = {base} · (1 + 0,004 · {temperature - reference}) = "
                  f"{decimal_text(measured)} Ом."],
    )


def _stopping(seed: int, profile: ProfileSource) -> dict:
    k, reaction, braking = _digits(seed, 23, 3, 2)
    speed, time, deceleration = 10 + k, 1 + Fraction(reaction, 2), 5 * (1 + braking)
    distance = speed * time + Fraction(speed * speed, 2 * deceleration)
    linear = 2 * deceleration * time
    root = linear + 2 * speed
    return _task(
        profile, seed, "stopping-distance",
        statement=("Автомобиль движется со скоростью v ≥ 0 м/с. За время реакции t "
                   "скорость не меняется, затем автомобиль тормозит с постоянным "
                   "замедлением a до полной остановки. Остановочный путь "
                   "s = vt + v²/(2a) не должен превышать свободный путь из таблицы. "
                   "Найдите наибольшую допустимую скорость в км/ч."),
        formula=r"s=vt+\frac{v^2}{2a},\qquad v\geq 0", answer=Fraction(18 * speed, 5),
        table=_table(("Время реакции", time, "с"), ("Замедление", deceleration, "м/с²"),
                     ("Свободный путь", distance, "м")),
        difficulty=2, estimated_seconds=210,
        hints=["Предельная скорость достигается при равенстве пути доступному расстоянию.",
               "После умножения на 2a получается v² + 2atv − 2as = 0; нужен корень v ≥ 0.",
               f"В уравнении v² + {decimal_text(linear)}v − "
               f"{decimal_text(2 * deceleration * distance)} = 0 вычислите дискриминант. "
               "Переведите положительный корень из м/с в км/ч умножением на 3,6."],
        solution=[f"На границе v² + {decimal_text(linear)}v − "
                  f"{decimal_text(2 * deceleration * distance)} = 0. "
                  f"Дискриминант равен {decimal_text(root * root)} = "
                  f"({decimal_text(root)})².",
                  f"Корни: {speed} и {decimal_text(-linear - speed)} м/с. "
                  "Отрицательный корень не соответствует скорости.",
                  "При увеличении неотрицательного v оба слагаемых пути возрастают. "
                  f"Поэтому {speed} м/с — максимум; {speed} · 3,6 = "
                  f"{decimal_text(Fraction(18 * speed, 5))} км/ч."],
    )


def _catch_up(seed: int, profile: ProfileSource) -> dict:
    k, gap, increment = _digits(seed, 23, 3, 3)
    slow, delay, difference = 40 + k, 30 * (1 + gap), (10, 20, 25)[increment]
    fast = slow + difference
    lead = Fraction(slow * delay, 60)
    time = lead / difference
    return _task(
        profile, seed, "catch-up-motion",
        statement=("Первый автомобиль выехал из пункта A. Второй выехал из A позже "
                   "на указанное в таблице время и движется по той же дороге в том же "
                   "направлении. Скорости постоянны, остановок нет, дорога достаточно "
                   "длинная. Через сколько часов после своего выезда второй догонит первого?"),
        formula=None, answer=time,
        table=_table(("Скорость первого", slow, "км/ч"), ("Скорость второго", fast, "км/ч"),
                     ("Задержка", delay, "мин")),
        hints=["Отсчитывайте искомое время от выезда второго автомобиля.",
               "Отрыв равен v₁Δt, а скорость его сокращения — v₂ − v₁; Δt нужна в часах.",
               f"Разделите отрыв {slow} · ({delay}/60) км на разность скоростей "
               f"{fast} − {slow} км/ч."],
        solution=[f"Задержка {delay}/60 = {decimal_text(Fraction(delay, 60))} ч; "
                  f"начальный отрыв {decimal_text(lead)} км.",
                  f"Скорость сближения {fast} − {slow} = {difference} км/ч. "
                  f"Время {decimal_text(lead)}/{difference} = {decimal_text(time)} ч.",
                  f"Проверка путей: второй проходит {decimal_text(fast * time)} км, "
                  f"первый — {slow} · ({decimal_text(time)} + "
                  f"{decimal_text(Fraction(delay, 60))}) = {decimal_text(fast * time)} км."],
    )


def _river(seed: int, profile: ProfileSource) -> dict:
    k, flow, down_hours, up_hours = _digits(seed, 23, 4, 3, 2)
    own, current, down_time, up_time = 12 + k, 2 + flow, 2 + down_hours, 3 + up_hours
    downstream, upstream = (own + current) * down_time, (own - current) * up_time
    return _task(
        profile, seed, "river-speed-system",
        statement=("Катер прошёл один участок по течению, а другой против течения. "
                   "Расстояния и время движения указаны в таблице. Собственная скорость "
                   "катера и скорость течения постоянны и одинаковы на обоих участках; "
                   "остановок нет. Найдите скорость течения в км/ч."),
        formula=None, answer=current,
        table=_table(("Путь по течению", downstream, "км"),
                     ("Время по течению", down_time, "ч"),
                     ("Путь против течения", upstream, "км"),
                     ("Время против течения", up_time, "ч")),
        hints=["Разделите каждый путь на его время, чтобы получить две скорости "
               "относительно берега.",
               "Если u — скорость катера, c — течения, то u + c = s₁/t₁, u − c = s₂/t₂.",
               f"Вычтите из {downstream}/{down_time} величину {upstream}/{up_time} "
               "и разделите разность на два."],
        solution=[f"Скорости относительно берега: {downstream}/{down_time} = "
                  f"{own + current} и {upstream}/{up_time} = {own - current} км/ч.",
                  f"Из системы u + c = {own + current}, u − c = {own - current} "
                  f"получаем 2c = {2 * current}, c = {current} км/ч.",
                  f"Собственная скорость u = {own} км/ч больше {current} км/ч; "
                  "движение против течения возможно. Обе скорости восстанавливают данные пути."],
    )


def _pumps(seed: int, profile: ProfileSource) -> dict:
    k, first, second = _digits(seed, 23, 3, 2)
    scale, p, q = 1 + k, 1 + first, 2 + first + second
    a, b, together = p * (p + q) * scale, q * (p + q) * scale, p * q * scale
    return _task(
        profile, seed, "joint-pumps",
        statement=("Два насоса заполняют один и тот же пустой резервуар. В таблице указано, "
                   "за сколько часов каждый насос заполняет его в одиночку. Их расходы "
                   "постоянны и при совместной работе не меняются, утечек нет. За сколько "
                   "часов оба насоса, включённые одновременно, заполнят резервуар?"),
        formula=None, answer=together,
        table=_table(("Первый насос отдельно", a, "ч"), ("Второй насос отдельно", b, "ч")),
        hints=["Примите объём резервуара за единицу и найдите долю, поступающую за час.",
               "Складываются производительности: 1/T = 1/t₁ + 1/t₂.",
               f"Найдите сумму 1/{a} + 1/{b}, затем возьмите обратное число."],
        solution=[f"Часовые производительности равны 1/{a} и 1/{b} резервуара в час.",
                  f"За T часов заполнится T/{a} + T/{b} = 1. "
                  f"Отсюда T = ({a} · {b})/({a} + {b}) = {together} ч.",
                  f"Время {together} ч меньше каждого из {a} и {b} ч. "
                  "Сумма заполненных долей при подстановке равна единице."],
    )


def _production(seed: int, profile: ProfileSource) -> dict:
    k, early, multiplier = _digits(seed, 23, 4, 4)
    planned_days, saved_days, scale = 10 + k, 2 + early, 2 + multiplier
    planned_rate = (planned_days - saved_days) * scale
    increase, order = saved_days * scale, planned_days * planned_rate
    return _task(
        profile, seed, "production-deadline",
        statement=("Мастерская должна изготовить заказ. Плановая дневная выработка "
                   "постоянна. Увеличив её на указанное число изделий, мастерская "
                   "выполнила весь заказ на несколько дней раньше. В таблице даны объём "
                   "заказа, прирост выработки и сокращение срока. Рабочие дни одинаковы, "
                   "брака и простоев нет. Найдите плановую выработку в изделиях за день."),
        formula=None, answer=planned_rate, difficulty=2, estimated_seconds=240,
        table=_table(("Объём заказа", order, "шт."),
                     ("Прирост выработки", increase, "шт./день"),
                     ("Сокращение срока", saved_days, "дней")),
        hints=["Объём заказа одинаков; при большей выработке время равно объёму, делённому на неё.",
               "Обозначьте плановую выработку x > 0. Разность сроков: N/x − N/(x + d) = e.",
               f"После умножения на x(x + {increase}) решите "
               f"x² + {increase}x − {order * scale} = 0 и выберите положительный корень."],
        solution=[f"Уравнение сроков: {order}/x − {order}/(x + {increase}) = {saved_days}.",
                  f"При x > 0 оно равносильно x² + {increase}x − {order * scale} = 0. "
                  f"Корни {planned_rate} и {-planned_rate - increase}; второй отрицателен.",
                  f"Плановый срок {order}/{planned_rate} = {planned_days} дней, фактический "
                  f"{order}/{planned_rate + increase} = {planned_days - saved_days} дней. "
                  f"Разность равна {saved_days}, как в условии."],
    )


def _dilution(seed: int, profile: ProfileSource) -> dict:
    k, target_part, ratio_part = _digits(seed, 23, 3, 3)
    mass, target, ratio = 10 + k, 5 + 5 * target_part, 2 + ratio_part
    initial, water = target * ratio, mass * (ratio - 1)
    return _task(
        profile, seed, "solution-dilution",
        statement=("К раствору соли добавляют только чистую воду. Исходная масса, "
                   "исходная и требуемая массовые концентрации даны в таблице. "
                   "Соль не выпадает в осадок, испарения и потерь нет. Сколько "
                   "килограммов воды нужно добавить для получения требуемой концентрации?"),
        formula=None, answer=water,
        table=_table(("Исходная масса", mass, "кг"), ("Исходная концентрация", initial, "%"),
                     ("Требуемая концентрация", target, "%")),
        hints=["При добавлении чистой воды масса соли сохраняется, а общая масса растёт.",
               "Если добавили x кг, то m · c₁/100 = (m + x) · c₂/100.",
               f"Решите {mass} · {initial} = ({mass} + x) · {target}; проверьте x > 0."],
        solution=[f"Исходная масса соли {mass} · {initial}/100 = "
                  f"{decimal_text(Fraction(mass * initial, 100))} кг.",
                  f"Баланс соли: {mass} · {initial} = ({mass} + x) · {target}. "
                  f"Конечная масса {mass * ratio} кг, поэтому x = {water} кг.",
                  f"Добавленная вода положительна. После разбавления отношение массы соли "
                  f"к {mass * ratio} кг равно {target}/100, исходная соль сохранена."],
    )


def _alloy(seed: int, profile: ProfileSource) -> dict:
    k, lower, upper, portion = _digits(seed, 23, 4, 5, 4)
    scale, low, high, part = 10 + k, 10 + 5 * lower, 60 + 5 * upper, 1 + portion
    total, target, first = 5 * scale, Fraction(part * low + (5 - part) * high, 5), part * scale
    return _task(
        profile, seed, "alloy-balance",
        statement=("Два сплава содержат медь и другой металл. Из них без потерь "
                   "переплавляют новый сплав заданной массы и массовой доли меди. "
                   "Содержание меди в каждом исходном сплаве и в результате дано "
                   "в таблице. Сколько килограммов первого, менее богатого медью сплава "
                   "нужно взять? Используются оба исходных сплава."),
        formula=None, answer=first, difficulty=2, estimated_seconds=180,
        table=_table(("Масса сплава", total, "кг"), ("Первый сплав", low, "%"),
                     ("Второй сплав", high, "%"), ("Требуемое содержание", target, "%")),
        hints=["Запишите отдельно сохранение общей массы и сохранение массы меди.",
               "Для масс x и y: x + y = M, c₁x + c₂y = cM; проценты можно сократить на 100.",
               f"Подставьте y = {total} − x в {low}x + {high}y = "
               f"{decimal_text(target)} · {total}."],
        solution=[f"Пусть x и y — массы исходных сплавов. Система: x + y = {total}, "
                  f"{low}x + {high}y = {decimal_text(target * total)}.",
                  f"После исключения y: ({high} − {low})x = "
                  f"{decimal_text(total * (high - target))}. Значит, x = {first} кг.",
                  f"Тогда y = {total - first} кг. Обе массы положительны; "
                  f"{low} · {first} + {high} · {total - first} = "
                  f"{decimal_text(target * total)}, баланс меди соблюдён."],
    )


def _line(seed: int, profile: ProfileSource) -> dict:
    k, steepness, direction, shift = _digits(seed, 23, 4, 2, 7)
    x1, y1 = -4 + shift, -10 + k
    slope = Fraction((1 + 2 * steepness) * (-1 if direction else 1), 2)
    x2, y2, target = x1 + 4, y1 + 4 * slope, x1 + 6
    answer = y1 + slope * (target - x1)
    description = (f"Прямая f проходит через A({x1}; {y1}) и "
                   f"B({x2}; {decimal_text(y2)}). Оси имеют обычные координатные единицы. "
                   "Иные точки являются продолжением той же прямой.")
    figure = _figure(description, [[(x1 - 1, y1 - slope), (x2 + 1, y2 + slope)]],
                     [("A", x1, y1), ("B", x2, y2)])
    return _task(
        profile, seed, "line-reconstruction",
        statement=("График линейной функции — прямая через отмеченные точки A и B. "
                   "Их координаты и аргумент, для которого нужно найти значение, "
                   "даны в таблице. Восстановите зависимость и найдите значение функции "
                   "при указанном аргументе."),
        formula=r"f(x)=kx+b", answer=answer, figure=figure,
        table=_table(("Абсцисса A", x1, "ед."), ("Ордината A", y1, "ед."),
                     ("Абсцисса B", x2, "ед."), ("Ордината B", y2, "ед."),
                     ("Аргумент", target, "ед.")),
        hints=["Наклон прямой определяется изменением ординаты при изменении абсциссы.",
               "Найдите k = (yB − yA)/(xB − xA), затем используйте f(x) = yA + k(x − xA).",
               f"Разность абсцисс равна 4, разность ординат — {decimal_text(y2 - y1)}. "
               f"От A до нужного аргумента {target - x1} координатных единиц."],
        solution=[f"k = ({decimal_text(y2)} − ({y1}))/({x2} − ({x1})) = "
                  f"{decimal_text(slope)}.",
                  f"f(x) = {y1} + ({decimal_text(slope)})(x − ({x1})). "
                  "Подстановка обеих данных точек подтверждает модель.",
                  f"f({target}) = {y1} + ({decimal_text(slope)}) · {target - x1} = "
                  f"{decimal_text(answer)}."],
    )


def _parabola(seed: int, profile: ProfileSource) -> dict:
    k, magnitude, direction = _digits(seed, 23, 3, 2)
    h, vertical, a = -4 + k % 9, k - 11, (1 + magnitude) * (-1 if direction else 1)
    px, py, target = h + 2, vertical + 4 * a, h + 3
    points = [(h + Fraction(i, 8), vertical + a * Fraction(i, 8)**2)
              for i in range(-16, 17)]
    description = (f"Показан участок параболы с вершиной V({h}; {vertical}) и "
                   f"отмеченной точкой P({px}; {py}). Ось симметрии вертикальна; "
                   "координаты этих точек точно заданы таблицей.")
    return _task(
        profile, seed, "parabola-vertex",
        statement=("График квадратичной функции имеет вершину V и проходит через P. "
                   "Координаты и нужный аргумент указаны в таблице. Используйте вид "
                   "f(x) = a(x − h)² + k, где V(h; k), и найдите значение функции "
                   "при заданном аргументе."),
        formula=r"f(x)=a(x-h)^2+k,\quad a\ne 0", answer=vertical + 9 * a,
        figure=_figure(description, [points], [("V", h, vertical), ("P", px, py)]),
        table=_table(("Абсцисса вершины", h, "ед."),
                     ("Ордината вершины", vertical, "ед."),
                     ("Абсцисса P", px, "ед."), ("Ордината P", py, "ед."),
                     ("Аргумент", target, "ед.")),
        hints=["Координаты вершины сразу задают два сдвига; неизвестен только коэффициент a.",
               "Подставьте точку P: a = (yP − k)/(xP − h)².",
               f"Квадрат смещения точки P равен 4. Разделите {py} − ({vertical}) "
               "на 4 и подставьте нужный аргумент."],
        solution=[f"Вершинная форма: f(x) = a(x − ({h}))² + ({vertical}).",
                  f"Точка P даёт {py} = 4a + ({vertical}), поэтому a = {a}.",
                  f"f({target}) = {a} · ({target} − ({h}))² + ({vertical}) = "
                  f"{vertical + 9 * a}. Знак a согласуется с направлением ветвей."],
    )


def _reciprocal(seed: int, profile: ProfileSource) -> dict:
    k, horizontal, direction = _digits(seed, 23, 5, 2)
    x, y = 1 + horizontal, (1 + k) * (-1 if direction else 1)
    coefficient = x * y
    # Every displayed rational coordinate terminates; no tolerance is needed.
    xs = sorted({Fraction(1, 2), Fraction(5, 8), Fraction(4, 5), Fraction(1),
                 Fraction(5, 4), Fraction(8, 5), Fraction(2), Fraction(5, 2),
                 Fraction(4), Fraction(5), Fraction(8), Fraction(x)})
    description = (f"Правая ветвь графика f(x) = k/x, x не равен нулю, проходит "
                   f"через A({x}; {y}). Отмеченная точка задана точно; соединённые "
                   "точки показывают форму ветви, ось x = 0 не входит в область определения.")
    return _task(
        profile, seed, "reciprocal-parameter",
        statement=("На рисунке показана часть графика обратной пропорциональности "
                   "f(x) = k/x, k ≠ 0. Координаты отмеченной точки A даны в таблице. "
                   "Определите параметр k."),
        formula=r"f(x)=\frac{k}{x},\quad x\ne 0", answer=coefficient,
        figure=_figure(description, [[(value, coefficient / value) for value in xs]],
                       [("A", x, y)]),
        table=_table(("Абсцисса A", x, "ед."), ("Ордината A", y, "ед.")),
        hints=["Для обратной пропорциональности произведение координат любой точки постоянно.",
               "Из y = k/x при x ≠ 0 получаем k = xy.",
               f"Умножьте абсциссу {x} на ординату {y}, сохраняя знак."],
        solution=[f"Подставляем точку A: {y} = k/{x}; абсцисса ненулевая.",
                  f"Умножаем на {x}: k = {x} · ({y}) = {coefficient}.",
                  f"Проверка: {coefficient}/{x} = {y}. При положительном x знак "
                  "ординаты совпадает со знаком параметра, как на рисунке."],
    )


def _exponential(seed: int, profile: ProfileSource) -> dict:
    k, ratio = _digits(seed, 23, 4)
    scale, base = 2 + k, (Fraction(2), Fraction(3), Fraction(4), Fraction(1, 2))[ratio]
    at_one, answer = scale * base, scale * base**3
    description = (f"Отмечены две точки зависимости f(x) = c·a^x: (0; {scale}) и "
                   f"(1; {decimal_text(at_one)}). Кривая между ними не проведена. "
                   "Вид функции задан условием, точки задают её параметры.")
    return _task(
        profile, seed, "exponential-data",
        statement=("Зависимость имеет вид f(x) = c·a^x, где c > 0, a > 0 и a ≠ 1. "
                   "Таблица и рисунок задают значения при нуле и единице. "
                   "Восстановите оба параметра и найдите значение при аргументе из таблицы."),
        formula=r"f(x)=c a^x,\quad c>0,\ a>0,\ a\ne 1", answer=answer,
        figure=_figure(description, [], [("A", 0, scale), ("B", 1, at_one)]),
        table=_table(("Значение при нуле", scale, "ед."),
                     ("Значение при единице", at_one, "ед."), ("Аргумент", 3, "ед.")),
        hints=["При нулевом показателе степень равна единице, поэтому первое значение даёт c.",
               "Параметры: c = f(0), a = f(1)/f(0). Затем вычислите c·a³.",
               f"Разделите {decimal_text(at_one)} на {scale}; найденный множитель "
               "примените три раза к значению при нуле."],
        solution=[f"f(0) = c·1 = {scale}, значит c = {scale}.",
                  f"a = f(1)/c = {decimal_text(at_one)}/{scale} = {decimal_text(base)}.",
                  f"f(3) = {scale} · ({decimal_text(base)})³ = {decimal_text(answer)}. "
                  "Оба параметра удовлетворяют ограничениям модели."],
    )


def _intersection(seed: int, profile: ProfileSource) -> dict:
    k, first, second, height = _digits(seed, 23, 3, 3, 7)
    cross_x, cross_y, m, n = -5 + k, -3 + height, 1 + first, -1 - second
    b, c = cross_y - m * cross_x, cross_y - n * cross_x
    left, right = min(0, cross_x) - 1, max(1, cross_x) + 1
    description = (f"Первая прямая проходит через (0; {b}) и (1; {m + b}), "
                   f"вторая — через (0; {c}) и (1; {n + c}). "
                   "Обе прямые продолжаются за показанный участок; координаты точек точные.")
    return _task(
        profile, seed, "line-intersection",
        statement=("Таблица задаёт значения двух линейных функций при x = 0 и x = 1. "
                   "На рисунке изображены их прямые. Найдите абсциссу единственной "
                   "точки пересечения графиков."),
        formula=None, answer=cross_x,
        figure=_figure(description, [[(left, m * left + b), (right, m * right + b)],
                                     [(left, n * left + c), (right, n * right + c)]],
                       [("f", 0, b), ("g", 0, c)]),
        table=_table(("Первая при нуле", b, "ед."), ("Первая при единице", m + b, "ед."),
                     ("Вторая при нуле", c, "ед."), ("Вторая при единице", n + c, "ед.")),
        hints=["В точке пересечения обе функции имеют одинаковую ординату при одной абсциссе.",
               "Восстановите каждую прямую: b = f(0), k = f(1) − f(0), затем приравняйте значения.",
               f"Решите {m}x + ({b}) = ({n})x + ({c})."],
        solution=[f"Из таблицы f(x) = {m}x + ({b}), g(x) = ({n})x + ({c}).",
                  f"Равенство ординат даёт ({m} − ({n}))x = {c} − ({b}); x = {cross_x}.",
                  f"При этом обе ординаты равны {cross_y}. Наклоны {m} и {n} различны, "
                  "поэтому точка пересечения единственна."],
    )


def _polyline(seed: int, profile: ProfileSource) -> dict:
    k, summit, end = _digits(seed, 23, 4, 4)
    base, peak, last = k - 10, 5 + summit, 8 + 3 * end
    points = [(-4, base), (-1, base + peak), (2, base + 2), (5, base + last)]
    at_left, at_right = base + Fraction(2 * peak, 3), base + 4 + end
    answer = max(base + peak, at_right)
    description = ("График — ломаная, последовательно соединяющая точки "
                   + ", ".join(f"{name}({x}; {y})" for name, (x, y)
                               in zip("ABCD", points, strict=True))
                   + ". Между соседними точками функция линейна. Исследуется отрезок [-2; 3].")
    # at_left may be a recurring rational, so it is written as an exact fraction in the solution.
    return _task(
        profile, seed, "polyline-maximum",
        statement=("График функции — ломаная ABCD; между соседними вершинами зависимость "
                   "линейная. Координаты вершин и границы исследуемого отрезка даны "
                   "в таблице. Найдите наибольшее значение функции на этом отрезке, "
                   "включая его концы."),
        formula=None, answer=answer, difficulty=2, estimated_seconds=180,
        figure=_figure(description, [points], [(name, x, y) for name, (x, y)
                                              in zip("ABCD", points, strict=True)]),
        table=_table(*[(name, value, "ед.") for letter, (x, y)
                       in zip("ABCD", points, strict=True)
                       for name, value in ((f"Абсцисса {letter}", x), (f"Ордината {letter}", y))],
                     ("Левая граница", -2, "ед."), ("Правая граница", 3, "ед.")),
        hints=["Учитывайте только заданный отрезок, даже если вне него график поднимается выше.",
               "У линейного участка максимум на конце; сравните внутренние вершины "
               "и концы отрезка.",
               f"Внутри лежат B и C. Для правого конца x = 3 пройдена треть от C к D: "
               f"f(3) = {base + 2} + ({last - 2})/3."],
        solution=[f"На отрезке [-2; 3] кандидаты: x = -2, -1, 2, 3. "
                  f"На первом участке f(-2) = {base} + 2·{peak}/3 = {at_left}.",
                  f"В вершинах f(-1) = {base + peak}, f(2) = {base + 2}. "
                  f"На последнем участке f(3) = {base + 2} + {last - 2}/3 = {at_right}.",
                  f"Сравнение четырёх значений даёт максимум {answer}. "
                  "Вершина D вне исследуемого отрезка и не участвует в сравнении."],
    )


def _percentages(seed: int, profile: ProfileSource) -> dict:
    k, rise_part, fall_part = _digits(seed, 23, 5, 5)
    initial, rise, discount = 1000 + 100 * k, 10 + 5 * rise_part, 10 + 5 * fall_part
    raised = initial * (1 + Fraction(rise, 100))
    final = raised * (1 - Fraction(discount, 100))
    return _task(
        profile, seed, "successive-percentages",
        statement=("В начале первого месяца цену товара повысили на процент из таблицы. "
                   "В начале второго месяца предоставили указанную скидку от уже "
                   "повышенной цены. Других изменений, платежей и сборов нет. "
                   "Найдите окончательную цену товара в рублях."),
        formula=None, answer=final,
        table=_table(("Начальная цена", initial, "руб."), ("Повышение", rise, "%"),
                     ("Скидка", discount, "%")),
        hints=["Для второго изменения базой является цена после первого месяца.",
               "Повышению на p% соответствует множитель 1 + p/100, скидке q% — 1 − q/100.",
               f"Последовательно умножьте {initial} на {decimal_text(1 + Fraction(rise, 100))} "
               f"и {decimal_text(1 - Fraction(discount, 100))}."],
        solution=[f"После повышения цена {initial} · "
                  f"{decimal_text(1 + Fraction(rise, 100))} = {decimal_text(raised)} руб.",
                  f"Скидка составляет {discount}% от {decimal_text(raised)} руб., "
                  f"то есть {decimal_text(raised * discount / 100)} руб.",
                  f"Итог {decimal_text(raised)} − "
                  f"{decimal_text(raised * discount / 100)} = {decimal_text(final)} руб."],
    )


def _deposit(seed: int, profile: ProfileSource) -> dict:
    k, rate_part, periods = _digits(seed, 23, 9, 2)
    principal, rate, years = 10000 * (10 + k), 4 + rate_part, 2 + periods
    factor = 1 + Fraction(rate, 100)
    balances = [principal * factor**year for year in range(years + 1)]
    return _task(
        profile, seed, "capitalized-deposit",
        statement=("Вклад открыли однократным взносом на срок из таблицы. Годовая ставка "
                   "постоянна. В конце каждого полного года проценты начисляются на "
                   "текущий остаток и сразу присоединяются к вкладу. Пополнений, снятий, "
                   "налогов и комиссий нет. После последнего начисления вклад закрывают. "
                   "Какую общую сумму в рублях получит вкладчик?"),
        formula=None, answer=balances[-1], estimated_seconds=150,
        table=_table(("Первоначальный вклад", principal, "руб."),
                     ("Годовая ставка", rate, "%"), ("Срок", years, "лет")),
        hints=["Составьте последовательность остатков после каждого годового начисления.",
               "При капитализации Bᵢ = Bᵢ₋₁(1 + r/100); исходный остаток равен взносу.",
               f"Умножьте {principal} на {decimal_text(factor)} ровно {years} раза."],
        solution=[f"Годовой множитель {decimal_text(factor)}; первый остаток "
                  f"{decimal_text(balances[1])} руб.",
                  *[f"После года {year}: {decimal_text(balances[year - 1])} · "
                    f"{decimal_text(factor)} = {decimal_text(balances[year])} руб."
                    for year in range(2, years + 1)],
                  f"Возвращаются весь остаток {decimal_text(balances[-1])} руб., "
                  f"то есть взнос {principal} руб. и проценты "
                  f"{decimal_text(balances[-1] - principal)} руб. Округления не потребовалось."],
    )


def _paid_interest(seed: int, profile: ProfileSource) -> dict:
    k, rate_part, periods = _digits(seed, 23, 9, 3)
    principal, rate, quarters = 20000 + 2000 * k, 4 + rate_part, 4 + 2 * periods
    payment = Fraction(principal * rate, 400)
    return _task(
        profile, seed, "paid-interest-deposit",
        statement=("Вклад открыт одним взносом на указанное число полных кварталов. "
                   "Годовая простая ставка дана в таблице: за каждый квартал начисляется "
                   "ровно четверть годовой ставки от первоначального взноса. В конце "
                   "квартала проценты переводят на отдельный беспроцентный счёт; "
                   "капитализации нет. После последней выплаты возвращают весь взнос. "
                   "Пополнений, досрочного снятия, налогов и комиссий нет. Сколько рублей "
                   "процентов получит вкладчик за весь срок, без учёта возврата взноса?"),
        formula=None, answer=payment * quarters,
        table=_table(("Первоначальный вклад", principal, "руб."),
                     ("Годовая ставка", rate, "%"), ("Срок", quarters, "кварталов")),
        hints=["База для процентов каждый квартал одна и та же: проценты выводятся со вклада.",
               "Квартальная выплата равна P·r/400; сложите выплаты за все кварталы.",
               f"Найдите четверть от {rate}% суммы {principal} руб. и умножьте на {quarters}."],
        solution=[f"За квартал выплачивается {principal} · {rate}/400 = "
                  f"{decimal_text(payment)} руб.",
                  f"За {quarters} кварталов проценты составят {decimal_text(payment)} · "
                  f"{quarters} = {decimal_text(payment * quarters)} руб.",
                  f"В конце отдельно возвращают {principal} руб. Общие поступления "
                  f"{decimal_text(principal + payment * quarters)} руб., "
                  "но вопрос касается только процентов."],
    )


def _principal_credit(seed: int, profile: ProfileSource) -> dict:
    k, term, rate_part = _digits(seed, 23, 6, 11)
    years, rate, part = 3 + term, 5 + rate_part, 10000 + 500 * k
    principal = years * part
    interest = Fraction(principal * rate * (years + 1), 200)
    return _task(
        profile, seed, "equal-principal-credit",
        statement=("Кредит выдан единовременно на число полных лет из таблицы. "
                   "В конце каждого года сначала начисляют проценты по указанной "
                   "годовой ставке на долг после предыдущего платежа, затем заёмщик "
                   "платит все начисленные проценты и одну равную долю первоначального "
                   "основного долга. Число долей равно числу лет. Последний платёж "
                   "полностью погашает кредит. Других платежей, налогов и комиссий нет. "
                   "Найдите общую сумму всех платежей в рублях."),
        formula=None, answer=principal + interest, difficulty=2, estimated_seconds=240,
        table=_table(("Сумма кредита", principal, "руб."), ("Годовая ставка", rate, "%"),
                     ("Срок", years, "лет")),
        hints=["Равны доли основного долга, а не полные годовые платежи.",
               "Долги перед начислениями: P, P − P/n, …, P/n. Проценты равны r/100 от их суммы.",
               f"Доля основного долга равна {principal}/{years} = {part} руб. "
               f"Сложите {years} остатков от {principal} до {part} и начислите {rate}%."],
        solution=[f"Основной долг каждый год уменьшается на {part} руб.; "
                  f"остатки перед начислениями: {principal}, {principal - part}, …, {part} руб.",
                  f"Сумма этих остатков ({principal} + {part}) · {years}/2 = "
                  f"{principal * (years + 1) // 2} руб. Проценты за срок "
                  f"{decimal_text(interest)} руб.",
                  f"Всего возвращают основной долг {principal} и проценты "
                  f"{decimal_text(interest)}: {decimal_text(principal + interest)} руб. "
                  "После последней равной доли и её процентов остаток равен нулю."],
    )


def _equal_payment(seed: int, profile: ProfileSource) -> dict:
    k, rate_part = _digits(seed, 23, 4)
    scale, rate = 200 + 10 * k, 5 + 5 * rate_part
    principal, factor = (200 + rate) * scale, 1 + Fraction(rate, 100)
    payment = Fraction(scale * (100 + rate)**2, 100)
    after_first = principal * factor - payment
    return _task(
        profile, seed, "equal-payment-credit",
        statement=("Кредит выдан на два полных года. В конце каждого года сначала "
                   "начисляют проценты по постоянной годовой ставке на текущий долг, "
                   "затем вносится платёж. Оба платежа равны; второй полностью "
                   "погашает долг вместе с начисленными процентами. Сумма кредита, "
                   "ставка и срок даны в таблице. Других платежей, налогов и комиссий "
                   "нет. Найдите размер одного платежа в рублях."),
        formula=None, answer=payment, difficulty=2, estimated_seconds=240,
        table=_table(("Сумма кредита", principal, "руб."), ("Годовая ставка", rate, "%"),
                     ("Срок", 2, "лет")),
        hints=["Запишите остаток после первого платежа; именно на него начислят "
               "проценты второго года.",
               "При q = 1 + r/100 и платеже A: B₁ = Pq − A, B₂ = (Pq − A)q − A = 0.",
               f"Раскройте скобки: A(q + 1) = {principal}q², где q = {decimal_text(factor)}."],
        solution=[f"После первого года и платежа A долг равен {principal} · "
                  f"{decimal_text(factor)} − A.",
                  f"Полное погашение: ({principal} · {decimal_text(factor)} − A) · "
                  f"{decimal_text(factor)} − A = 0. Отсюда A = Pq²/(q + 1) = "
                  f"{decimal_text(payment)} руб.",
                  f"После первого платежа остаётся {decimal_text(after_first)} руб.; "
                  f"после следующего начисления {decimal_text(after_first)} · "
                  f"{decimal_text(factor)} = {decimal_text(payment)} руб. "
                  "Второй платёж закрывает долг точно."],
    )


def _budget(seed: int, profile: ProfileSource) -> dict:
    k, home, food_part, travel, save = _digits(seed, 23, 5, 5, 5, 3)
    income, housing = 60000 + 1000 * k, 16000 + 500 * home
    food, transport = 14000 + 500 * food_part, 3000 + 250 * travel
    percent = 10 + 5 * save
    reserve = Fraction(income * percent, 100)
    result = income - housing - food - transport - reserve
    return _task(
        profile, seed, "family-budget",
        statement=("Семья планирует бюджет одного календарного месяца. Доход в таблице "
                   "указан после налогов. В начале расчётного месяца свободный остаток "
                   "равен нулю. Все обязательные расходы за этот месяц приведены в таблице; "
                   "долгов и других поступлений нет. Семья также переводит указанную "
                   "долю всего месячного дохода на отдельный резервный счёт без процентов "
                   "и комиссий. Сколько рублей останется для остальных покупок после "
                   "обязательных расходов и перевода в резерв?"),
        formula=None, answer=result,
        table=_table(("Доход", income, "руб."), ("Жильё", housing, "руб."),
                     ("Питание", food, "руб."), ("Транспорт", transport, "руб."),
                     ("Доля в резерв", percent, "%")),
        hints=["Отделите обязательные расходы от резервирования и определите базу процента.",
               "Свободные деньги = доход − обязательные расходы − доход·доля резерва/100.",
               f"Сначала найдите {percent}% от {income}, затем вычтите резерв "
               "и три статьи расходов."],
        solution=[f"Резерв: {income} · {percent}/100 = {decimal_text(reserve)} руб.",
                  f"Обязательные расходы: {housing} + {food} + {transport} = "
                  f"{housing + food + transport} руб.",
                  f"Остаётся {income} − {housing + food + transport} − "
                  f"{decimal_text(reserve)} = {decimal_text(result)} руб. "
                  "Резерв остаётся собственностью семьи, но недоступен для текущих покупок."],
    )


def _tariff(seed: int, profile: ProfileSource) -> dict:
    k, rate_part, difference_part = _digits(seed, 23, 4, 3)
    threshold, first, difference = 100 + 5 * k, 7 + rate_part, 1 + difference_part
    fixed, second = threshold * difference, first - difference
    return _task(
        profile, seed, "tariff-threshold",
        statement=("Для месячного потребления электричества сравнивают два учебных тарифа. "
                   "Первый не имеет постоянной платы: оплачивается каждый кВт·ч. "
                   "Второй включает фиксированную месячную плату плюс цену каждого кВт·ч. "
                   "Ставки из таблицы действуют на весь объём, лимитов и дополнительных "
                   "сборов нет. Рассматриваются только неотрицательные целые числа кВт·ч. "
                   "При каком наименьшем таком потреблении второй тариф строго дешевле первого?"),
        formula=None, answer=threshold + 1, difficulty=2, estimated_seconds=180,
        table=_table(("Первый тариф", first, "руб./кВт·ч"),
                     ("Плата второго", fixed, "руб./месяц"),
                     ("Второй тариф", second, "руб./кВт·ч")),
        hints=["Постройте две стоимости за один и тот же месяц при потреблении x.",
               "Нужно строгое неравенство F + b·x < a·x при целом x ≥ 0.",
               f"Решите {fixed} < ({first} − {second})x; равенство ещё не означает выгоду."],
        solution=[f"Месячные стоимости: C₁ = {first}x, C₂ = {fixed} + {second}x.",
                  f"Второй дешевле при {fixed} < {difference}x, то есть x > {threshold}.",
                  f"Наименьшее целое x = {threshold + 1}. При {threshold} кВт·ч цены равны, "
                  f"при {threshold + 1} второй дешевле на {difference} руб."],
    )


FAMILIES = (
    Family("heat-balance", 10, "Теплота: подстановка и две смены единиц",
           ("applied-substitution", "applied-units", "applied-plausibility"), _heat, True),
    Family("pressure-force", 10, "Сила из формулы давления",
           ("applied-isolate-variable", "applied-units"), _pressure),
    Family("tank-net-flow", 10, "Баланс воды и границы модели",
           ("applied-simple-model", "applied-isolate-variable", "applied-constraints",
            "applied-plausibility"), _tank),
    Family("resistance-temperature", 10, "Температура по показанию датчика",
           ("applied-isolate-variable", "applied-substitution", "applied-constraints"),
           _resistance),
    Family("stopping-distance", 10, "Допустимая скорость и остановочный путь",
           ("applied-isolate-variable", "applied-units", "applied-constraints",
            "applied-plausibility"), _stopping, True),
    Family("catch-up-motion", 11, "Движение вдогонку с задержкой старта",
           ("word-motion", "word-equation-model"), _catch_up, True),
    Family("river-speed-system", 11, "Скорости катера и течения: система",
           ("word-motion", "word-system-model"), _river),
    Family("joint-pumps", 11, "Совместная работа двух насосов",
           ("word-work-rate", "word-equation-model"), _pumps, True),
    Family("production-deadline", 11, "Изменение выработки и срока заказа",
           ("word-work-rate", "word-equation-model"), _production),
    Family("solution-dilution", 11, "Разбавление раствора чистой водой",
           ("word-mixtures", "word-equation-model"), _dilution),
    Family("alloy-balance", 11, "Два сплава: баланс массы и металла",
           ("word-mixtures", "word-system-model"), _alloy),
    Family("line-reconstruction", 12, "Прямая по двум точкам",
           ("function-reconstruction", "function-values", "function-parameters"), _line, True),
    Family("parabola-vertex", 12, "Парабола по вершине и точке",
           ("function-reconstruction", "function-values", "function-parameters"), _parabola, True),
    Family("reciprocal-parameter", 12, "Параметр обратной пропорциональности",
           ("function-reconstruction", "function-parameters"), _reciprocal),
    Family("exponential-data", 12, "Показательная зависимость по двум значениям",
           ("function-reconstruction", "function-values", "function-parameters"), _exponential),
    Family("line-intersection", 12, "Пересечение двух прямых из таблицы",
           ("function-reconstruction", "function-intersections"), _intersection),
    Family("polyline-maximum", 12, "Максимум ломаной на заданном отрезке",
           ("function-values", "function-graph-properties"), _polyline),
    Family("successive-percentages", 13, "Последовательные изменения цены",
           ("finance-percentages", "finance-period-changes"), _percentages),
    Family("capitalized-deposit", 13, "Вклад с ежегодной капитализацией",
           ("finance-percentages", "finance-period-changes", "finance-deposits"), _deposit, True),
    Family("paid-interest-deposit", 13, "Вклад с выплатой процентов каждый квартал",
           ("finance-percentages", "finance-period-changes", "finance-deposits",
            "finance-payments"), _paid_interest),
    Family("equal-principal-credit", 13, "Кредит с равными долями основного долга",
           ("finance-percentages", "finance-period-changes", "finance-credit",
            "finance-payments"), _principal_credit, True),
    Family("equal-payment-credit", 13, "Кредит с двумя равными платежами",
           ("finance-period-changes", "finance-credit", "finance-payments"), _equal_payment),
    Family("family-budget", 13, "Семейный бюджет с резервом",
           ("finance-percentages", "finance-personal-family-budget"), _budget),
    Family("tariff-threshold", 13, "Выбор тарифа и строгая граница выгоды",
           ("finance-other-models", "finance-personal-family-budget", "finance-payments"), _tariff),
)
_BY_ID = {family.id: family for family in FAMILIES}


def _section(heading: str, body: str, formula: str | None = None) -> dict:
    return {"heading": heading, "body": " ".join(body.split()), "formula": formula}


_LESSONS = {
    "heat-balance": {
        "minutes": 5,
        "takeaway": "Массу переведите в килограммы, вычислите разность температур; "
                    "полученные джоули переведите в килоджоули только в конце.",
        "sections": [
            _section("Что измеряет количество теплоты", """
                Этот способ нужен, когда известная физическая формула связывает несколько
                величин, а вопрос требует аккуратной подстановки. Количество теплоты показывает,
                сколько энергии получило тело при нагревании. Масса характеризует количество
                вещества, удельная теплоёмкость показывает затраты энергии на нагрев одного
                килограмма на один градус. Разность температур описывает именно изменение
                состояния воды. Поэтому в произведение входит не конечная температура сама
                по себе. Если вода была тёплой до включения нагревателя, часть её внутренней
                энергии уже существовала и повторно не прибавляется. Модель предполагает
                постоянную теплоёмкость, отсутствие потерь и отсутствие кипения. Эти условия
                объясняют, почему достаточно одной формулы вместо подробного описания нагревателя.
            """, r"Q=cm(T_2-T_1)"),
            _section("Приводим массу к нужной единице", """
                Единицу массы выбирают по записи теплоёмкости. Если она дана в джоулях
                на килограмм и градус, масса должна быть в килограммах. Перевод граммов
                означает деление на тысячу: количество воды при этом не меняется, меняется
                только число, выражающее его в выбранной единице. Например, семьсот пятьдесят
                граммов составляют три четверти килограмма. Удобно записать такую массу
                обыкновенной дробью и сократить её с другими множителями. Десятичная запись
                также допустима, если она точная. Нельзя подставить граммы и надеяться,
                что последующий перевод джоулей исправит ошибку: это два разных преобразования.
                Подпишите единицу рядом с каждым исходным числом до начала вычисления.
            """),
            _section("Разность температур и порядок действий", """
                Сначала вычтите начальную температуру из конечной. При нагревании результат
                положителен. Для разности температур один градус Цельсия соответствует одному
                кельвину, поэтому прибавлять к обеим температурам какое-либо число не требуется.
                Затем умножьте массу, теплоёмкость и найденную разность. Скобки важны:
                сначала получается изменение температуры, потом выполняется умножение.
                Размерности сокращаются: килограммы и градусы из числителя уничтожают такие
                же единицы в знаменателе теплоёмкости, остаются джоули. Если спрашивают
                килоджоули, разделите полученную энергию на тысячу. Так единица ответа
                определяется вычислением, а не числом нулей или внешним видом результата.
                Промежуточные дроби сохраняйте точно, иначе итог уже не будет точным
                значением модели.
            """),
            _section("Проверка смысла и типичных ошибок", """
                Удвоение массы при прежнем нагреве должно удвоить количество теплоты.
                Удвоение разности температур действует так же. Эти мысленные изменения
                позволяют заметить случайное деление вместо умножения. При равных начальной
                и конечной температурах формула даёт нуль, а при охлаждении значение
                отрицательно: тело отдаёт энергию. В нашей задаче требуется положительная
                полученная теплота. Проверьте, что температура остаётся ниже температуры
                кипения и не появляется необходимость учитывать фазовый переход. Самые
                частые арифметические ловушки здесь связаны с использованием конечной
                температуры вместо её изменения и с несогласованной массой. Перед записью
                ответа восстановите цепочку единиц и убедитесь, что последнее число выражено
                именно в килоджоулях, как просит условие.
            """),
        ],
    },
    "pressure-force": {
        "minutes": 5,
        "takeaway": "Сначала выразите F = pS; перевод площади требует квадрата коэффициента длины.",
        "sections": [
            _section("От определения к неизвестной силе", """
                Давление описывает распределение силы по площади контакта. Одна и та же
                сила на меньшей площади создаёт большее давление: поэтому острая кромка
                действует иначе, чем широкая опора. В определении давление равно отношению
                силы к площади. Если неизвестна сила, не нужно подбирать действие по словам
                «больше» или «меньше»: выразите её алгебраически. Площадь положительна,
                поэтому можно умножить обе части равенства на неё. Деление на площадь
                справа исчезает, а слева получается произведение давления и площади.
                Такой приём работает и в других прикладных формулах: сначала назовите
                искомую величину, затем выполните одинаковое обратимое действие с обеими
                частями исходного равенства, сохраняя его смысл.
            """, r"p=\frac{F}{S}\quad\Longrightarrow\quad F=pS"),
            _section("Почему квадратные сантиметры особенные", """
                Перевод площади отличается от перевода длины. В одном метре сто
                сантиметров, но квадрат со стороной один метр содержит сто рядов
                по сто квадратных сантиметров. Поэтому квадратный метр содержит десять
                тысяч квадратных сантиметров. Число квадратных сантиметров при переходе
                к квадратным метрам делят на десять тысяч. Коэффициент линейного
                перевода возводится в квадрат вместе с единицей. Чтобы не заучивать
                нули, представьте прямоугольник и переведите в метры обе его стороны,
                а затем перемножьте их. Использование делителя сто означало бы перевод
                только одной стороны. Именно такая ошибка увеличивает вычисленную силу
                в сто раз, даже если остальные действия выполнены безупречно.
            """),
            _section("Согласуем давление и площадь", """
                Паскаль — это ньютон на квадратный метр. Приставка «кило» означает
                тысячу, поэтому значение давления в килопаскалях умножают на тысячу
                для получения паскалей. Теперь сила вычисляется в ньютонах: паскали
                умножаются на квадратные метры, единицы площади сокращаются. Полезно
                написать преобразования двумя отдельными строками, чтобы не смешать
                увеличение численного значения давления и уменьшение численного значения
                площади. При данных в килопаскалях и квадратных сантиметрах общий
                числовой коэффициент произведения равен одной десятой. Это сокращение
                можно применять после вывода, а не вместо понимания единиц. Сохраняйте
                точную дробь, пока не получите конечный результат, и не приписывайте
                к нему единицы давления: спрашивается именно сила.
            """),
            _section("Проверяем обратным действием", """
                Разделите найденную силу на площадь в квадратных метрах. Должно
                получиться заданное давление в паскалях. Такая обратная проверка
                одновременно контролирует преобразование формулы и единицы. Отдельно
                проверьте качественную зависимость: при неизменном давлении увеличение
                площади требует увеличения силы. Это отличается от ситуации, когда
                постоянной считают силу и обсуждают изменение давления. Название
                постоянной величины здесь принципиально. Нулевая площадь не допускается,
                поскольку исходное определение содержит деление; отрицательная площадь
                не описывает поверхность опоры. В рассматриваемой модели давление
                равномерное, поэтому вся площадь участвует одинаково. Если бы давление
                менялось по поверхности, подстановка одного произвольного значения
                уже не описывала бы полную силу без дополнительной информации.
            """),
        ],
    },
    "tank-net-flow": {
        "minutes": 5,
        "takeaway": "Запас меняется с чистой скоростью приток минус отток; время допустимо "
                    "только до опустошения или переполнения.",
        "sections": [
            _section("Составляем баланс вместо готовой формулы", """
                Задача о баке учит строить простую модель по описанию процесса.
                Важно различать запас и расход. Запас измеряется литрами и говорит,
                сколько воды находится внутри в выбранный момент. Расход измеряется
                литрами за минуту и показывает изменение за единицу времени.
                Если одновременно работают подача и слив, складывать их расходы
                как два притока нельзя. За каждую минуту запас увеличивается на
                поступившую воду и уменьшается на вытекшую. Разность этих величин
                называется чистым притоком. Положительный чистый приток означает
                заполнение, отрицательный — опустошение, нулевой — неизменность запаса.
                Начальный объём не является ещё одним расходом: это отдельное
                слагаемое, с которого начинается отсчёт изменения воды.
            """),
            _section("От одной минуты к произвольному времени", """
                При постоянных расходах изменение за несколько минут пропорционально
                длительности. Умножьте чистый приток на время и прибавьте начальный
                объём. В полученной формуле все слагаемые измеряются литрами:
                расход умножается на минуты, поэтому единица времени сокращается.
                Если время требуется в часах, сначала согласуйте его с расходами
                или переведите окончательный результат. Для нахождения момента
                достижения нужного уровня приравняйте объём требуемому. Перенесите
                начальный запас и разделите оставшийся прирост на чистый приток.
                Это обычное линейное уравнение, но смысл его частей помогает
                выбрать знаки. Вычитается начальная вода, потому что её не нужно
                набирать заново, а слив уменьшает скорость накопления.
            """, r"V(t)=V_0+(q_{\text{вх}}-q_{\text{вых}})t"),
            _section("Где заканчивается действие модели", """
                Линейное выражение само по себе может дать сколь угодно большой
                объём. Настоящий бак имеет вместимость, а отрицательный запас воды
                невозможен. Поэтому формула применяется только до достижения этих
                границ. Когда чистый приток положителен и требуемый объём лежит
                между начальным и вместимостью, вся траектория до ответа допустима.
                Достаточно проверить начальную и конечную точки, поскольку объём
                монотонно растёт. При переполнении часть поступающей воды уходит
                наружу, и прежний баланс запаса изменяется. При пустом баке нельзя
                продолжать считать постоянный слив. Такие события требуют нового
                участка модели. В наших заданиях числа выбраны так, чтобы искомый
                момент наступал до любого из этих событий.
            """),
            _section("Проверяем время и сохранение воды", """
                Положительное время должно отвечать движению от начального объёма
                к требуемому в нужную сторону. Если при положительном чистом
                притоке получилось отрицательное время, вероятно, перепутан порядок
                вычитания объёмов. Полезна проверка полного баланса: начальная вода
                плюс весь приток за найденное время равны конечной воде плюс
                весь отток за это же время. Она не зависит от сокращённой формулы
                и хорошо выявляет потерянное слагаемое. Затем оцените результат:
                при удвоении необходимого прироста с прежними расходами время
                удвоится, а при увеличении чистого притока уменьшится. Слово
                «впервые» не создаёт отдельного уравнения: при постоянном положительном
                чистом притоке один и тот же объём достигается ровно однажды.
            """),
        ],
    },
    "resistance-temperature": {
        "minutes": 5,
        "takeaway": "Из отношения R/R₀ сначала получите относительный прирост, затем изменение "
                    "температуры; опорную температуру прибавьте последней.",
        "sections": [
            _section("Опорное значение и относительное изменение", """
                Датчик переводит физическое состояние в измеряемое сопротивление.
                Чтобы восстановить температуру, нужно прочитать формулу в обратном
                направлении. Опорное сопротивление относится к заранее указанной
                температуре, а коэффициент показывает относительное изменение
                сопротивления при изменении температуры на один градус. Единица
                внутри скобок сохраняет начальное сопротивление: когда температура
                совпадает с опорной, температурная разность равна нулю, но
                сопротивление не исчезает. Поэтому зависимость сопротивления от
                температуры обычно нельзя считать прямой пропорциональностью.
                Удвоенное сопротивление не обязано означать удвоенную температуру.
                Сначала выделите, к какой исходной точке относятся оба изменения,
                и только затем переходите к вычислениям по показанию прибора.
            """, r"R=R_0(1+\alpha(T-T_0))"),
            _section("Последовательно снимаем действия", """
                При прямом расчёте из температуры сначала вычитают опорную,
                результат умножают на коэффициент, прибавляют единицу и умножают
                на опорное сопротивление. Обратный расчёт идёт в противоположном
                порядке. Разделите измеренное сопротивление на опорное, вычтите
                единицу, разделите на коэффициент и прибавьте опорную температуру.
                Каждое действие отменяет ровно одно внешнее действие исходной
                формулы. Скобки нельзя убирать произвольно: деление на коэффициент
                относится ко всему относительному приросту, а не только к единице.
                Деления допустимы, если опорное сопротивление и коэффициент ненулевые.
                В данной модели оба положительны. Сначала можно записать общий
                алгоритм буквами, а затем подставить числа в уже проверенное выражение.
            """, r"T=T_0+\frac{R/R_0-1}{\alpha}"),
            _section("Что означают промежуточные числа", """
                Отношение двух сопротивлений безразмерно: оно показывает, во сколько
                раз показание отличается от опорного значения. После вычитания
                единицы остаётся относительный прирост. Например, положительный
                прирост в одну десятую означает увеличение сопротивления на десятую
                часть исходного, а не увеличение температуры на десять градусов.
                Для перехода к температурной разности нужен коэффициент датчика.
                Его единица обратна градусу, поэтому деление безразмерного прироста
                на коэффициент даёт градусы. Только после этого можно складывать
                полученное число с опорной температурой. Такая проверка размерностей
                помогает обнаружить перестановку действий даже без численного ответа.
                Точные десятичные коэффициенты разрешается заменить обыкновенными
                дробями: это часто упрощает деление и исключает преждевременное округление.
            """),
            _section("Диапазон и обратная подстановка", """
                При положительном коэффициенте сопротивление выше опорного должно
                давать температуру выше опорной. Это первая быстрая проверка знака.
                Затем сравните результат с диапазоном, в котором производитель
                или условие гарантирует линейную модель. Алгебраический ответ за
                пределами диапазона не подтверждён этой зависимостью, даже если
                вычисления формально верны. В наших заданиях температура остаётся
                внутри указанного интервала. Для окончательной проверки вернитесь
                к исходной формуле: найдите температурную разность, умножьте её
                на коэффициент, прибавьте единицу и восстановите сопротивление.
                Оно должно точно совпасть с показанием. Если забыть прибавить опорную
                температуру после деления, вычисленная температура будет ниже правильной
                на T₀ градусов. При обратной подстановке сопротивление окажется меньше
                показания на R₀αT₀ Ом. Ошибка температуры измеряется градусами, а расхождение
                сопротивлений — омами.
            """),
        ],
    },
    "stopping-distance": {
        "minutes": 6,
        "takeaway": "Предельная скорость задаётся равенством путей; выберите неотрицательный "
                    "корень и лишь затем переведите м/с в км/ч.",
        "sections": [
            _section("Два участка остановочного пути", """
                Остановочный путь состоит из движения во время реакции и собственно
                торможения. Пока водитель реагирует, скорость по условию постоянна,
                поэтому пройденный путь равен скорости, умноженной на время реакции.
                После начала торможения модуль замедления постоянен, а тормозной
                путь пропорционален квадрату начальной скорости. Эти расстояния
                складываются, поскольку участки следуют друг за другом. Исключение
                первого слагаемого означало бы мгновенную реакцию, которой условие
                не предполагает. Исключение второго означало бы мгновенную остановку.
                Все величины внутри формулы должны быть согласованы: секунды,
                метры и метры в секунду. Заданное положительное замедление —
                модуль изменения скорости, поэтому перед квадратным слагаемым стоит плюс.
            """, r"s(v)=vt+\frac{v^2}{2a},\qquad t>0,\ a>0"),
            _section("Почему ищем граничное равенство", """
                Условие требует, чтобы остановочный путь не превышал доступное
                расстояние. Это неравенство, а вопрос спрашивает наибольшую скорость.
                При неотрицательной скорости увеличение скорости увеличивает и
                линейное, и квадратное слагаемое пути. Следовательно, путь возрастает,
                а предельное допустимое значение достигается на границе, где весь
                доступный путь использован точно. Значение ниже этой границы даёт
                меньший путь, значение выше — больший. Здесь достаточно сравнения
                двух слагаемых; производная не обязательна. Без ограничения на
                знак скорости такой аргумент нуждался бы в уточнении. Физический
                смысл величины позволяет сразу рассматривать только неотрицательную
                часть числовой оси и объясняет дальнейший отбор корня уравнения.
            """),
            _section("Квадратное уравнение и отбор корня", """
                Приравняйте путь доступному расстоянию и умножьте уравнение на
                удвоенное замедление. Этот множитель положителен и ненулевой,
                поэтому преобразование допустимо. Получится квадратное уравнение
                с положительным коэффициентом при линейном члене и отрицательным
                свободным членом. Его корни имеют разные знаки. Вычислите
                дискриминант точно, извлеките корень и выберите положительное
                решение. Отрицательное значение не подходит к неотрицательной
                скорости из условия, хотя удовлетворяет алгебраическому уравнению.
                Если корень записан дробью, сохраните её до перевода единиц.
                В параметрах этого семейства дискриминант специально является
                квадратом рационального числа, поэтому приближённое извлечение
                корня не требуется и точность не приходится задавать произвольно.
            """, r"v^2+2atv-2as=0"),
            _section("Перевод скорости и смысл максимума", """
                Найденный корень выражен в метрах в секунду, потому что именно
                эти единицы использованы в формуле. За час проходит три тысячи
                шестьсот секунд, а в километре тысяча метров. Поэтому численное
                значение скорости умножают на отношение этих чисел, то есть
                на три целых шесть десятых. Деление вместо умножения дало бы
                неверный перевод. Проверьте найденную скорость в исходной формуле
                до перевода: сумма двух участков должна точно равняться свободному
                пути. Затем мысленно увеличьте скорость: оба участка станут
                длиннее, и ограничение нарушится. Такая проверка подтверждает
                не только равенство, но и слово «наибольшая» в вопросе. Самостоятельный
                ответ запишите в требуемых километрах в час без дополнительных округлений.
            """),
        ],
    },
}


_LESSONS.update({
    "catch-up-motion": {
        "minutes": 5,
        "takeaway": "Выберите начало отсчёта: после старта второго первый уже имеет отрыв, "
                    "который сокращается с разностью скоростей.",
        "sections": [
            _section("Выбираем общие часы для двух участников", """
                В задачах вдогонку одинаковое место встречи не означает одинаковое
                время движения. Первый участник успевает двигаться ещё до старта
                второго. Удобно считать искомое время от выезда догоняющего,
                поскольку именно так обычно сформулирован вопрос. Тогда второй
                движется искомое время, а первый — это время плюс задержка старта.
                Нарисуйте небольшую временную линию с двумя моментами выезда
                и общим моментом встречи. Она помогает избежать случайного
                вычитания задержки. Если скорости заданы в километрах в час,
                задержку в минутах нужно перевести в часы. Путь вычисляется
                произведением согласованных скорости и времени; минуты нельзя
                прямо умножать на километры в час без перевода.
            """),
            _section("Смотрим на расстояние между автомобилями", """
                К моменту старта второго первый уже создал отрыв. Этот отрыв
                равен скорости первого, умноженной на задержку в часах.
                После старта второго оба продолжают движение в одном направлении.
                За каждый час первый тоже продвигается вперёд, поэтому отрыв
                сокращается не на всю скорость второго, а на разность скоростей.
                Если догоняющий быстрее, эта разность положительна. Разделив
                начальный отрыв на скорость его сокращения, получаем время
                до встречи. Если скорости равны, созданный отрыв сохраняется;
                если второй медленнее, он увеличивается. Таким образом, условие
                большей скорости догоняющего обеспечивает существование будущей
                встречи, а постоянство скоростей делает вычисляемый момент единственным.
            """, r"t=\frac{v_1\Delta t}{v_2-v_1}"),
            _section("То же рассуждение через уравнение путей", """
                Другой способ — выразить оба пути от общего пункта отправления.
                У второго путь равен его скорости, умноженной на искомое время.
                У первого в произведении стоит сумма искомого времени и задержки.
                В момент встречи эти пути равны. Раскрывая скобки и собирая
                слагаемые с неизвестным, получаем ту же формулу, что через
                начальный отрыв. Такое совпадение полезно: относительное движение
                объясняет смысл разности скоростей, а уравнение даёт проверку
                выбора времени. Не приравнивайте пути за одинаковые промежутки,
                если отсчёт начался в разные моменты. Именно дополнительное
                слагаемое пути первого кодирует задержку и отличает задачу
                вдогонку от одновременного выезда из одного пункта.
            """, r"v_2t=v_1(t+\Delta t)"),
            _section("Проверяем ответ и формулировку вопроса", """
                Подставьте найденное время в оба выражения путей. Они должны
                дать одно расстояние от пункта отправления. Затем убедитесь,
                что ответ положителен и относится ко второму выезду. Если
                вопрос был бы о времени после первого выезда, пришлось бы
                добавить задержку ещё раз, но к уже найденному результату,
                а не к уравнению без объяснения. При увеличении отрыва время
                встречи растёт, при увеличении разности скоростей уменьшается.
                Эти зависимости помогают заметить перевёрнутую дробь. Конечное
                десятичное число часов не является записью часов и минут:
                десятая доля часа содержит шесть минут. В самостоятельной
                записи сохраните единицу, указанную вопросом, и не заменяйте
                десятичную часть часов количеством минут после запятой.
            """),
        ],
    },
    "river-speed-system": {
        "minutes": 5,
        "takeaway": "Сначала найдите скорости относительно берега; половина их разности "
                    "равна скорости течения, половина суммы — собственной скорости.",
        "sections": [
            _section("Разделяем две системы отсчёта", """
                Собственная скорость катера — его скорость относительно воды.
                Путь по береговым ориентирам измеряет движение относительно берега.
                При движении по течению вода помогает катеру, поэтому береговая
                скорость равна сумме собственной скорости и скорости течения.
                Против течения вклад воды направлен противоположно, поэтому
                скорости вычитаются. Здесь скорость течения обозначается положительным
                числом, а знак выбирается направлением движения. Собственная
                скорость должна быть больше скорости течения, иначе катер
                не сможет продвигаться вверх по реке в описанном режиме.
                Предположение о постоянстве обеих скоростей позволяет использовать
                одну пару неизвестных для двух участков, даже когда расстояния
                и длительности этих участков различаются между собой.
            """),
            _section("Переходим от пути и времени к скоростям", """
                Не сравнивайте непосредственно расстояния вниз и вверх по реке:
                они могут быть разными из-за разных времён движения.
                Для каждого участка разделите путь на соответствующее время.
                Получатся две береговые скорости в одинаковых единицах.
                Если путь измеряется километрами, а время часами, результат
                выражен километрами в час. Если минуты встретились только
                на одном участке, переведите их до сравнения скоростей.
                Эти два вычисления превращают текстовые данные в простую
                систему: сумма неизвестных равна скорости по течению,
                разность равна скорости против течения. Так построение
                системы опирается на физический смысл каждой строки, а
                не на случайное расположение чисел в исходной таблице.
            """, r"u+c=\frac{s_1}{t_1},\qquad u-c=\frac{s_2}{t_2}"),
            _section("Решаем систему сложением и вычитанием", """
                При вычитании второго уравнения из первого собственные скорости
                уничтожаются, а скорость течения появляется дважды. Значит,
                разность береговых скоростей нужно разделить на два.
                Если вместо этого взять всю разность, течение будет завышено
                вдвое: его вклад уже присутствует с разными знаками в обеих
                строках системы. Сложение уравнений, наоборот, уничтожает течение
                и даёт удвоенную собственную скорость. Полусумма береговых
                скоростей здесь действительно имеет физический смысл, но это
                не средняя скорость всего путешествия. Средняя скорость поездки
                определяется общим путём и общим временем; при разных
                длительностях она вообще не обязана совпадать с полусуммой
                двух скоростей. Не смешивайте эти два разных вопроса.
            """),
            _section("Возвращаемся к исходным участкам", """
                После решения системы восстановите каждую береговую скорость
                и умножьте её на время соответствующего участка. Полученные
                расстояния должны совпасть с исходными. Эта проверка сохраняет
                связь алгебры с движением и обнаруживает переставленные
                времена. Затем проверьте ограничения: обе найденные скорости
                положительны, собственная больше течения, движение вверх
                по реке возможно. Если вычисленная скорость по течению
                оказалась меньше скорости против течения при неизменной
                работе катера, данные не отвечают принятой модели.
                В наших задачах параметры согласованы заранее, но при
                самостоятельном решении ограничения всё равно нужно назвать.
                В ответ переносится именно скорость течения, а не найденная
                попутно собственная скорость или скорость относительно берега.
            """),
        ],
    },
    "joint-pumps": {
        "minutes": 5,
        "takeaway": "Складывайте доли работы за час, затем берите обратную величину; "
                    "время совместной работы меньше каждого отдельного времени.",
        "sections": [
            _section("Условная единица работы", """
                Для задачи о совместной работе необязательно знать объём резервуара
                в литрах. Примите полное заполнение за единицу работы.
                Если насос один заполняет резервуар за несколько часов,
                за один час он выполняет обратную этому числу долю работы.
                Например, время в восемь часов означает одну восьмую
                резервуара за час. Это производительность, а не новое время.
                Чем больше время самостоятельного выполнения одного и того
                же задания, тем меньше производительность. Такой переход
                от времени к доле работы нужен потому, что при совместном
                действии суммируются поступающие объёмы воды. Длительности
                же нельзя складывать как объёмы: они характеризуют разные
                одиночные способы выполнения одной задачи.
            """),
            _section("Складываем производительности", """
                Каждый насос в течение одного часа вносит свою долю
                заполнения. При одновременном включении и независимой работе
                сумма этих долей даёт совместную производительность.
                Чтобы найти время заполнения целого резервуара, разделите
                единицу на найденную сумму. Иначе говоря, возьмите обратное
                число. При сложении обыкновенных дробей используйте общий
                знаменатель, затем сократите результат. Не заменяйте сумму
                производительностей средним значением времён: насосы работают
                одновременно, а не по очереди. Формула с произведением
                времён в числителе получается после приведения дробей
                к общему знаменателю, поэтому её полезно вывести самостоятельно.
                Тогда даже при непривычных числах вы сможете восстановить
                алгоритм из смысла производительности, не вспоминая готовый шаблон.
            """, r"\frac1T=\frac1{t_1}+\frac1{t_2},\qquad T=\frac{t_1t_2}{t_1+t_2}"),
            _section("Равенство выполненных долей", """
                Можно обозначить неизвестное время буквой и сразу записать,
                какую часть резервуара заполнит каждый насос за это время.
                Его доля равна отношению общего времени к времени
                одиночного заполнения. Сумма долей должна равняться единице.
                Получается линейное уравнение, равносильное расчёту совместной
                производительности. Этот вариант особенно удобен для проверки:
                подставьте найденное время и убедитесь, что части точно
                составляют целое. Если захотите использовать настоящий объём,
                обозначьте его отдельной буквой и выразите расходы через
                этот объём. Он сократится в уравнении, подтверждая законность
                выбора условной единицы. При этом ни один насос не
                должен заполнять целый резервуар отдельно до общего момента окончания.
            """),
            _section("Условия применимости и оценка", """
                Общая производительность больше производительности каждого насоса,
                поэтому совместное время меньше каждого одиночного времени.
                Это сильная проверка результата до подробной подстановки.
                При двух одинаковых насосах совместное время вдвое меньше
                одиночного, что даёт ещё один понятный контроль формулы.
                Модель предполагает постоянные расходы, отсутствие утечек
                и отсутствие взаимного влияния насосов. Если один насос
                включается позже, потребуется отдельный начальный этап,
                а если труба ограничивает общий расход, сумма одиночных
                производительностей может не работать. Такие условия нельзя
                незаметно добавлять или игнорировать. В данном семействе
                оба насоса включены одновременно и работают до заполнения.
                Итоговое число выражает часы, а не долю резервуара за час.
            """),
        ],
    },
    "production-deadline": {
        "minutes": 6,
        "takeaway": "При одинаковом объёме время равно объём/выработка; разность времён "
                    "строится до освобождения уравнения от знаменателей.",
        "sections": [
            _section("Один заказ и два режима работы", """
                В задаче сравниваются плановый и фактический способы выполнения
                одного заказа. Не меняется количество изделий, а меняются
                дневная выработка и необходимое число дней. Увеличение
                выработки сокращает срок, поэтому эти величины связаны
                обратной, а не прямой пропорциональностью. Удобно обозначить
                плановую выработку неизвестным положительным числом. Фактическая
                выработка тогда больше него на указанный прирост.
                Каждая выработка относится к рабочему дню одинаковой
                продолжительности. Предположения о постоянном режиме, отсутствии
                брака и простоев объясняют, почему весь заказ можно
                разделить на одну дневную выработку. Если производительность
                менялась по дням, одной такой дроби для срока уже было бы недостаточно.
            """),
            _section("Записываем разность сроков", """
                Плановый срок равен объёму заказа, делённому на плановую
                выработку. Фактический срок — тому же объёму, делённому
                на увеличенную выработку. Поскольку работу завершили раньше,
                из планового срока вычитают фактический. Разность должна
                совпасть с указанным сокращением числа дней. Перестановка
                дробей дала бы отрицательную разность и противоречила
                слову «раньше». Перед преобразованием запишите ограничение:
                плановая выработка положительна. Вместе с положительным
                приростом оно гарантирует ненулевые знаменатели. Размерности
                подтверждают модель: изделия, делённые на изделия за день,
                дают дни, поэтому обе части уравнения имеют одну единицу.
                На этом этапе текст задачи уже полностью переведён в алгебру.
            """, r"\frac{N}{x}-\frac{N}{x+d}=e,\qquad x>0"),
            _section("Освобождаем уравнение от дробей", """
                Умножьте равенство на произведение двух знаменателей. Благодаря
                записанному ограничению это преобразование допустимо. Слева
                разность произведений сокращается до объёма заказа, умноженного
                на прирост выработки; справа остаётся сокращение срока,
                умноженное на произведение выработок. После раскрытия
                скобок получается квадратное уравнение. Найдите его
                корни точным способом: через дискриминант или разложение
                на множители, если оно видно. Отрицательный корень
                не является плановой выработкой и отбрасывается по
                исходному ограничению. Не выбирайте корень только потому,
                что он выглядит «красивее». Отбор должен опираться
                на смысл неизвестного и на записанное условие положительности.
            """, r"e x(x+d)=Nd"),
            _section("Проверяем оба календарных срока", """
                Подстановка только в преобразованное квадратное уравнение
                не проверяет правильность перевода текста. Поэтому найдите
                по положительному корню оба срока исходными дробями
                и сравните их разность с условием. Одновременно убедитесь,
                что фактическая выработка больше плановой, а фактическое
                время меньше планового. В нашем семействе количество
                изделий и обе дневные выработки целые, а сроки
                соответствуют целым рабочим дням. Это исключает скрытый
                вопрос о неполном последнем дне. Ответ относится
                к плановой выработке, поэтому не переносите в него
                фактическую выработку или найденный срок. Подпись единиц
                на черновике помогает сохранить различие между изделиями,
                изделиями за день и числом рабочих дней во всём решении.
            """),
        ],
    },
    "solution-dilution": {
        "minutes": 5,
        "takeaway": "При разбавлении сохраняется масса соли; процент относится к новой "
                    "общей массе раствора, включающей добавленную воду.",
        "sections": [
            _section("Концентрация как отношение масс", """
                Массовая концентрация показывает, какую часть общей массы
                раствора составляет растворённое вещество. Процент переводится
                в долю делением на сто. Умножение массы раствора
                на эту долю даёт массу соли. Важно различать
                раствор и воду: исходный раствор уже содержит и
                воду, и соль. Указанная масса раствора относится
                ко всему содержимому сосуда. При добавлении чистой
                воды новая соль не поступает, но общая масса
                увеличивается. Поэтому концентрация уменьшается, хотя сама
                масса соли остаётся прежней. Это и есть основной
                закон модели разбавления, из которого можно вывести
                уравнение без запоминания отдельной формулы для каждой пары процентов.
            """),
            _section("Сохраняем то, что не меняется", """
                Обозначьте добавленную воду неизвестной массой. До разбавления
                массу соли найдите по исходной массе и исходной
                концентрации. После разбавления общая масса равна сумме
                исходного раствора и добавленной воды, а доля соли
                должна стать требуемой. Приравняйте два выражения массы
                соли. Делители сто присутствуют по обе стороны
                и могут быть сокращены общим умножением. Однако
                само понимание процентов при этом не исчезает:
                сокращение допустимо потому, что обе концентрации записаны
                одинаково. Если одна доля дана десятичной дробью,
                а другая процентом, сначала приведите их к одному
                представлению. Нельзя сравнивать процентное число и долю как одинаковые величины.
            """, r"m\frac{c_1}{100}=(m+x)\frac{c_2}{100}"),
            _section("Находим новую массу, затем добавку", """
                Решать уравнение можно двумя прозрачными шагами. Сначала
                разделите известную массу соли на требуемую долю,
                получив полную массу конечного раствора. Затем вычтите
                исходную массу: оставшаяся разность и есть добавленная
                вода. Это помогает не спутать добавку с конечным
                содержимым сосуда. При алгебраическом решении получается
                то же выражение: исходная масса умножается на
                отношение исходной концентрации к требуемой, после
                чего вычитается исходная масса. Если концентрацию
                уменьшают в несколько раз, во столько же
                раз увеличивается общая масса при неизменной соли.
                Вода, которую добавляют, составляет лишь прирост этой массы,
                поэтому её количество меньше полной массы полученного раствора.
            """),
            _section("Допустимость разбавления и проверка", """
                Добавлением чистой воды можно уменьшить положительную
                концентрацию, но нельзя увеличить её. Требуемая
                концентрация должна быть строго между нулём и
                исходной, если добавляется положительная конечная масса
                воды. Получение точно нулевой концентрации из раствора
                с солью потребовало бы удаления соли, чего
                модель не разрешает. После вычисления проверьте
                положительность добавки и восстановите концентрацию делением
                неизменной массы соли на новую общую массу.
                Полученная доля должна совпасть с требуемой точно.
                Испарение, осадок и потери изменили бы баланс,
                поэтому их отсутствие существенно. Оценивайте также направление:
                чем ниже требуемая концентрация при прежнем растворе,
                тем больше воды понадобится добавить до нужного состояния.
            """),
        ],
    },
    "alloy-balance": {
        "minutes": 6,
        "takeaway": "Две неизвестные массы определяются двумя балансами: общей массы "
                    "и массы меди; итоговая концентрация лежит между исходными.",
        "sections": [
            _section("Два независимых закона сохранения", """
                При смешивании двух сплавов неизвестны массы обоих
                исходных материалов. Одного равенства общей массы
                недостаточно: одну и ту же итоговую массу
                можно составить многими способами. Второе равенство
                задаёт количество выбранного металла, например меди.
                Если переплавка идёт без потерь и химических
                изменений, сохраняются и общая масса, и масса
                меди. Массовую долю каждого исходного сплава
                переводят в дробь и умножают на его
                массу. Сумма этих двух количеств меди должна
                равняться количеству меди в готовом сплаве.
                Так физическое содержание задачи естественно приводит
                к системе двух линейных уравнений для двух неизвестных масс.
            """),
            _section("Проценты не складываются сами по себе", """
                Средняя концентрация зависит не только от исходных
                концентраций, но и от количества каждого сплава.
                Простое среднее арифметическое верно лишь при равных
                массах. Если более богатого сплава взять больше,
                итоговая доля окажется ближе к его концентрации.
                Именно поэтому в уравнение входят произведения
                концентраций на массы. Общий делитель сто
                можно сократить во всех слагаемых одного
                баланса, если все концентрации записаны процентами.
                Массы должны быть в одной единице:
                килограммы нельзя складывать с граммами до
                перевода. Полезно составить таблицу с колонками
                «масса сплава», «доля меди», «масса меди»;
                она показывает, откуда берётся каждое произведение в уравнении.
            """, r"x+y=M,\qquad c_1x+c_2y=cM"),
            _section("Исключаем одну неизвестную", """
                Из баланса общей массы выразите массу второго
                сплава как итоговую массу минус массу первого.
                Подставьте это выражение в баланс меди.
                Получится одно линейное уравнение: после раскрытия
                скобок соберите члены с неизвестным слева,
                остальные справа. Поскольку исходные концентрации различны,
                коэффициент при неизвестном не равен нулю.
                Поэтому решение единственно. Удобно организовать
                вычитание так, чтобы в числителе и
                знаменателе получились положительные разности: для
                менее богатого сплава используются разность богатой
                и требуемой концентраций и разность богатой
                и бедной концентраций. Найдя первую массу,
                обязательно вычислите вторую: она понадобится для проверки системы целиком.
            """, r"x=M\frac{c_2-c}{c_2-c_1},\qquad c_1<c<c_2"),
            _section("Проверяем возможность получить нужный состав", """
                При использовании положительных количеств обоих сплавов
                итоговая концентрация строго между исходными.
                Если требуемая доля выходит за эти
                границы, одной переплавкой без добавок нужный
                состав получить нельзя. Совпадение с одной
                исходной концентрацией означало бы нулевое количество
                другого сплава, если исходные доли различны.
                После решения проверьте положительность обеих масс,
                их сумму и суммарную массу меди.
                Проверять только общую массу недостаточно: неверная
                смесь может иметь правильный вес. Затем
                соотнесите найденную величину с вопросом: требуется
                именно первый, менее богатый медью сплав.
                Дополнительная оценка через близость итоговой доли
                к одной из исходных помогает заметить переставленные массы двух материалов.
            """),
        ],
    },
})


_LESSONS.update({
    "line-reconstruction": {
        "minutes": 5,
        "takeaway": "Для прямой постоянна дробь изменение y / изменение x; "
                    "после наклона достаточно одной точки для восстановления зависимости.",
        "sections": [
            _section("Читаем координаты и вид зависимости", """
                Запись точки содержит сначала абсциссу, затем ординату.
                Для графика функции это означает: при указанном
                аргументе функция имеет указанное значение. Две
                точки не определяют произвольную функцию, поскольку
                через них можно провести много различных кривых.
                Но если условие заранее сообщает, что график
                является прямой, двух точек с различными
                абсциссами достаточно. Мы восстанавливаем линейную
                зависимость, а не угадываем её по внешнему
                виду рисунка. Подписи координат и таблица
                важнее визуального наклона: масштабы осей могут
                отличаться. Поэтому не измеряйте угол прямой
                на экране транспортиром и не принимайте
                видимую крутизну за численное значение коэффициента без проверки координат.
            """, r"f(x)=kx+b"),
            _section("Наклон как отношение приращений", """
                При переходе между двумя точками найдите изменение
                ординаты и изменение абсциссы. Их отношение
                равно угловому коэффициенту прямой. Порядок вычитания
                должен совпадать в числителе и знаменателе:
                либо везде вторая координата минус первая,
                либо везде наоборот. Одновременная смена порядка
                меняет оба знака и сохраняет результат.
                Смена порядка только в одной разности
                переворачивает знак наклона. Разные абсциссы
                обеспечивают ненулевой знаменатель. Если ординаты
                растут вместе с абсциссами, наклон положителен;
                если убывают, отрицателен. Одинаковые ординаты
                дают горизонтальную прямую с нулевым наклоном.
                Дробный коэффициент допустим и часто удобнее
                хранить его точной дробью, чем преждевременно переводить в приближённую запись.
            """, r"k=\frac{y_B-y_A}{x_B-x_A}"),
            _section("Восстанавливаем значение в нужной точке", """
                После нахождения наклона можно определить свободный
                член подстановкой любой известной точки.
                Но для вычисления одного значения часто
                проще использовать форму через приращение:
                к известной ординате прибавить наклон,
                умноженный на изменение аргумента от известной
                точки до искомой. Это та же
                линейная функция, записанная относительно удобной
                опоры. Такая форма уменьшает число действий
                с отрицательными свободными членами. Если
                искомый аргумент выходит за промежуток
                между данными точками, вычисление всё
                равно допустимо: условие задаёт всю
                прямую, а не только отрезок.
                Для неизвестной зависимости подобное продолжение
                было бы предположением, поэтому заранее установленный вид функции принципиален.
            """, r"f(x)=y_A+k(x-x_A)"),
            _section("Контроль двух данных и формата ответа", """
                Подставьте в восстановленную формулу обе известные
                абсциссы. Должны получиться обе ординаты
                из условия, а не только та,
                которой пользовались для нахождения свободного
                члена. Это выявляет ошибку в наклоне.
                Затем проверьте направление изменения до
                нужного аргумента: при положительном наклоне
                увеличение аргумента повышает значение функции.
                Учитывайте, что отрицательная ордината допустима,
                поскольку задача не задаёт физическую
                величину, обязанную быть положительной.
                Если спрашивают значение функции, ответом
                является ордината, а не найденный
                коэффициент или абсцисса. Отмеченный рисунок
                служит дополнительным представлением данных; точное
                число получается из координат и линейной модели, без приблизительного
                чтения пикселей.
            """),
        ],
    },
    "parabola-vertex": {
        "minutes": 5,
        "takeaway": "Вершина задаёт сдвиги: f(x) = a(x − h)² + k; "
                    "точка вне оси симметрии определяет оставшийся коэффициент.",
        "sections": [
            _section("Вершинная форма вместо трёх неизвестных", """
                Квадратичную функцию можно записать через три
                коэффициента общего многочлена, но координаты
                вершины предлагают более короткий путь.
                В вершинной форме горизонтальный сдвиг
                равен абсциссе вершины, вертикальный —
                её ординате. При подстановке абсциссы
                вершины квадрат обнуляется, поэтому значение
                функции сразу совпадает с её
                ординатой. Неизвестным остаётся только множитель
                перед квадратом. Он определяет направление
                ветвей и растяжение графика. Эта
                запись использует данную информацию прямо,
                поэтому не требуется составлять систему
                для трёх коэффициентов общего вида.
                Условие о квадратичной функции существенно:
                одна вершина и одна точка не задают любую произвольную кривую однозначно.
            """, r"f(x)=a(x-h)^2+k"),
            _section("Знаки сдвигов и симметрия", """
                Внутри скобок из аргумента вычитается
                абсцисса вершины. Если она отрицательна,
                вычитание отрицательного числа превращается
                в сложение. Полезно не заменять
                знаки мысленно, а сначала записать
                координату вершины в скобках целиком.
                Для проверки подставьте эту координату:
                выражение под квадратом обязано исчезнуть.
                Аргументы на равных расстояниях слева
                и справа от вершины дают
                одинаковые значения, потому что квадраты
                противоположных чисел равны. Это объясняет
                вертикальную ось симметрии. Ордината вершины
                прибавляется после возведения в квадрат
                и умножения; её нельзя включать
                внутрь квадрата, иначе получится другой сдвиг и другая функция с иными данными.
            """),
            _section("Находим коэффициент по дополнительной точке", """
                Подставьте координаты дополнительной точки в
                вершинную форму. Вычтите ординату вершины
                и разделите результат на квадрат
                горизонтального смещения этой точки.
                Дополнительная точка должна иметь абсциссу,
                отличную от абсциссы вершины. Иначе
                знаменатель равнялся бы нулю, а
                точка не давала бы новой
                информации о множителе. Знак найденного
                коэффициента согласуется с рисунком:
                положительный направляет ветви вверх,
                отрицательный вниз. После восстановления
                коэффициента подставьте нужный аргумент,
                сначала вычислите смещение, затем
                его квадрат, затем произведение
                и вертикальный сдвиг. Возведение всего выражения в квадрат вместо одного смещения
                нарушило бы этот порядок и изменило бы зависимость.
            """, r"a=\frac{y_P-k}{(x_P-h)^2}"),
            _section("Чем помогают свойства параболы", """
                У положительного множителя вершина даёт
                наименьшее значение всей квадратичной
                функции, у отрицательного — наибольшее.
                Поэтому значение в другой точке
                должно лежать с нужной стороны
                от ординаты вершины. Это проверяет
                знак и порядок действий независимо
                от арифметики. Подстановка известной
                дополнительной точки должна возвращать
                её ординату точно. Для нового
                аргумента можно также найти
                симметричный относительно вершины и
                убедиться, что значения совпадают.
                Рисунок показывает лишь участок
                параболы, но заданная квадратичная
                модель действует для любого вещественного аргумента. Поэтому вычисление за пределами
                показанного участка возможно без визуального продолжения кривой и без округления.
                При удвоении расстояния от оси симметрии разность между значением функции
                и ординатой вершины увеличивается в четыре раза, а не в два.
            """),
        ],
    },
    "reciprocal-parameter": {
        "minutes": 5,
        "takeaway": "У обратной пропорциональности произведение xy постоянно; "
                    "ненулевая точка даёт k = xy с учётом знака.",
        "sections": [
            _section("Одна точка при известном виде функции", """
                Обратная пропорциональность описывается отношением
                постоянного параметра к аргументу.
                График такой зависимости является
                гиперболой, если параметр ненулевой.
                Здесь вид функции уже сообщён,
                поэтому одной подходящей точки
                достаточно для определения единственного
                неизвестного параметра. Если бы
                вид зависимости не был задан,
                одна точка не позволяла бы
                восстановить функцию. Координаты читаются
                обычным способом: первая задаёт
                аргумент, вторая значение функции.
                На рисунке может быть показана
                только одна ветвь, но числовые
                подписи дают точную информацию. Не нужно оценивать кривизну или расстояние между
                графиком и осью на глаз: параметр определяется алгебраически по отмеченной точке.
            """, r"y=\frac{k}{x},\qquad k\ne0"),
            _section("Почему произведение координат постоянно", """
                Умножение исходного равенства на
                ненулевой аргумент освобождает его
                от знаменателя. Получается равенство
                параметра произведению координат.
                Поэтому при увеличении положительного
                аргумента в несколько раз
                ордината уменьшается во столько
                же раз, если параметр
                остаётся прежним. Это отличает
                обратную пропорциональность от прямой,
                где постоянно отношение координат.
                Формулы легко перепутать, если
                ориентироваться только на слово
                «пропорциональность». Сначала запишите
                заданный вид функции, затем
                выполните обратимое преобразование. При подстановке дробных координат
                произведение можно
                сократить точно. Деление ординаты на абсциссу в этом семействе определяло бы
                коэффициент совсем другой, прямо пропорциональной зависимости.
            """, r"k=xy"),
            _section("Знаки и область определения", """
                Аргумент не может быть
                равен нулю, поскольку в
                исходной формуле он находится
                в знаменателе. При ненулевом
                параметре ордината также не
                равна нулю. Если координаты
                отмеченной точки одного знака,
                параметр положителен; если разных,
                отрицателен. Положительный параметр размещает
                ветви в первой и
                третьей координатных четвертях,
                отрицательный — во второй
                и четвёртой. Эти признаки
                помогают проверить знак произведения.
                При отрицательной ординате не
                заменяйте её модулем только потому, что на рисунке отмечено расстояние вниз.
                Координата хранит направление относительно оси и должна входить в вычисление
                со своим знаком. Оси являются границами приближения ветвей, а не их частями.
            """),
            _section("Обратная проверка и чтение рисунка", """
                Разделите найденный параметр на
                абсциссу отмеченной точки.
                Должна получиться исходная ордината.
                Это короткая проверка исходного
                уравнения, а не только
                переписанного произведения. Дополнительно
                выберите другой допустимый аргумент
                и предскажите направление изменения
                значения. Например, при положительных
                координатах удвоение аргумента вдвое
                уменьшает ординату. Графическое изображение
                может соединять несколько вычисленных
                точек, поэтому точность чтения
                промежуточной ординаты ограничена изображением.
                В условии используются именно
                отмеченные точные данные. Ответом служит параметр, а не площадь произвольного
                прямоугольника на картинке, хотя произведение координат геометрически связано
                с такой площадью при положительных координатах. Сохраняйте знак и точную запись.
                Ни пересечение с вертикальной осью, ни нулевая ордината не могут быть
                дополнительными точками этой гиперболы при ненулевом параметре.
            """),
        ],
    },
    "exponential-data": {
        "minutes": 5,
        "takeaway": "Значение при нуле задаёт масштаб c; отношение f(1)/f(0) задаёт "
                    "множитель a, который повторяется при каждом единичном шаге аргумента.",
        "sections": [
            _section("Повторяется множитель, а не прибавка", """
                Показательная зависимость отличается от линейной
                тем, что при одинаковом
                увеличении аргумента повторяется отношение
                значений, а не их
                разность. В записи с
                множителем перед степенью этот
                множитель задаёт масштаб, а
                основание степени задаёт изменение
                за единичный шаг аргумента.
                Условие заранее сообщает такой
                вид зависимости, поэтому мы
                не выбираем между прямой
                и кривой по двум
                точкам. Через те же
                точки можно провести прямую,
                но она обычно даст другие значения при дальнейших аргументах. Две точки
                здесь используются для определения двух параметров уже выбранной модели,
                а не как доказательство показательного характера любого реального процесса.
            """, r"f(x)=c a^x,\qquad c>0,\quad a>0,\quad a\ne1"),
            _section("Начинаем со значения при нуле", """
                Любое положительное основание в
                нулевой степени равно единице.
                Поэтому значение функции при
                нуле совпадает с множителем
                перед степенью. Это делает
                нулевой аргумент удобной опорой:
                один параметр определяется без
                решения системы. Не принимайте
                нулевую степень за нуль,
                иначе исчезнет весь исходный
                масштаб. При аргументе один
                степень равна самому основанию.
                Значит, значение при единице
                равно масштабу, умноженному на
                основание. Разделив второе известное
                значение на первое, найдём основание. Деление допустимо, потому что масштаб
                положителен. Параметры теперь определены однозначно и позволяют вычислять
                остальные значения без приблизительного построения кривой между отмеченными точками.
            """, r"c=f(0),\qquad a=\frac{f(1)}{f(0)}"),
            _section("Вычисляем значение за несколько шагов", """
                При целом положительном аргументе
                степень означает повторное умножение
                на основание указанное число
                раз. Можно записать цепочку
                последовательных значений или сразу
                использовать степень. При этом
                масштаб умножается только один
                раз: его нельзя возводить
                в ту же степень
                вместе с основанием. Если
                основание является дробью, удобно
                возвести в степень отдельно
                числитель и знаменатель и
                сократить результат с масштабом.
                Обыкновенные дроби сохраняют точность.
                Разность первых двух значений не следует прибавлять на каждом шаге: это
                построило бы линейную зависимость. Для проверки очередное значение всегда
                должно иметь к предыдущему одно и то же отношение, равное основанию.
            """),
            _section("Рост, убывание и проверка параметров", """
                При основании больше единицы
                положительная функция возрастает:
                каждый шаг умножает значение
                на число больше единицы.
                При основании между нулём
                и единицей функция убывает,
                сохраняя положительность. Основание,
                равное единице, дало бы
                постоянную функцию и исключено
                условиями этого семейства.
                Неположительное основание не
                подходит к заданной модели
                для произвольного вещественного
                аргумента. После расчёта
                проверьте оба исходных значения
                подстановкой нуля и единицы. Затем оцените направление изменения до требуемого
                аргумента. Если убывающая модель внезапно дала отрицательный результат,
                ошибка находится в действиях с дробью или знаком, а не в допустимом
                поведении функции.
            """),
        ],
    },
    "line-intersection": {
        "minutes": 5,
        "takeaway": "Восстановите обе прямые из данных, приравняйте их значения "
                    "при одном x и проверьте найденную абсциссу в двух формулах.",
        "sections": [
            _section("Одна точка принадлежит двум графикам", """
                Пересечение графиков означает совпадение
                обеих координат точки.
                Недостаточно найти одинаковые
                значения функций при разных
                аргументах: это были бы
                две точки на одной
                горизонтали. У пересечения
                аргумент общий, и значения
                функций при нём равны.
                Поэтому задача сводится к
                уравнению равенства двух
                функций. Прежде чем составлять
                его, нужно восстановить сами
                зависимости из таблицы.
                Условие сообщает, что обе
                функции линейные, поэтому их значения при двух различных аргументах
                достаточны. Рисунок помогает увидеть предполагаемое положение пересечения,
                но точный ответ определяется исходными координатами, даже если точка
                выглядит нецелой.
            """),
            _section("Удобные аргументы нуль и единица", """
                Для линейной функции значение
                при нуле равно свободному
                члену. При переходе от
                нуля к единице аргумент
                изменяется на единицу,
                поэтому разность ординат
                сразу равна угловому
                коэффициенту. Выполните эти
                два действия отдельно для
                первой и второй функции.
                Не смешивайте значения
                из разных строк:
                каждая пара относится
                к своей прямой.
                Полезно подписать формулы
                разными буквами и проверить, что подстановка нуля и единицы возвращает
                соответствующие данные. Если свободный член отрицательный, сохраняйте
                его знак в скобках до аккуратного упрощения, особенно при дальнейшем
                переносе слагаемых между частями уравнения пересечения.
            """, r"b=f(0),\qquad k=f(1)-f(0)"),
            _section("Решаем уравнение равенства ординат", """
                Приравняйте две восстановленные
                линейные формулы при
                одном и том же
                неизвестном аргументе.
                Перенесите слагаемые с
                аргументом в одну
                сторону, свободные члены
                в другую. Коэффициент
                при неизвестном будет
                разностью наклонов прямых.
                Если наклоны различны,
                эта разность ненулевая
                и решение единственно.
                Именно такая ситуация
                дана в наших заданиях.
                При равных наклонах нужно было бы отдельно сравнивать свободные члены:
                разные дают параллельные прямые без пересечения, одинаковые — совпадающие
                графики с бесконечным числом общих точек. Такое рассмотрение объясняет,
                почему перед делением важна проверка ненулевого коэффициента,
                а не только техника решения.
            """, r"(k_1-k_2)x=b_2-b_1"),
            _section("Абсцисса и ордината — разные ответы", """
                Найденное решение уравнения
                является абсциссой пересечения.
                Подстановка его в
                любую формулу даёт
                ординату той же
                точки. Для проверки
                вычислите ординату дважды,
                по каждой прямой:
                значения обязаны совпасть.
                Если вопрос просит
                только абсциссу, не
                заменяйте её полученной
                ординатой и не
                записывайте пару координат
                вместо одного числа.
                Сопоставьте знак абсциссы с положением пересечения относительно вертикальной
                оси на рисунке. Проверка не требует измерять изображение: достаточно
                качественного соответствия сторон. Отрицательные координаты разрешены,
                поскольку линейные функции в этом задании определены на всей числовой
                прямой и не ограничены условиями физической модели или положительной области.
                Само равенство ординат проверяется численно в обеих формулах, поэтому
                совпадение нарисованных линий на экране не заменяет проверку точного решения.
            """),
        ],
    },
    "polyline-maximum": {
        "minutes": 6,
        "takeaway": "Максимум на отрезке ищите среди его концов и внутренних вершин; "
                    "высокие точки за границами отрезка не участвуют.",
        "sections": [
            _section("Сначала выделяем исследуемый отрезок", """
                График может быть
                изображён на большем
                промежутке, чем тот,
                о котором спрашивают.
                Поэтому сначала отметьте
                левую и правую
                границы исследования и
                мысленно оставьте только
                часть графика между
                ними. Наибольшее значение
                функции — самая высокая
                ордината этой части,
                а не самая
                большая абсцисса.
                Вершина справа за
                пределами отрезка может быть выше всех остальных, но не относится
                к допустимым аргументам. Закрытый отрезок включает обе граничные точки,
                поэтому их значения участвуют в сравнении. Это существенно, когда
                на возрастающем участке правый конец даёт значение выше внутренних вершин.
            """),
            _section("Почему достаточно конечного списка кандидатов", """
                Между соседними вершинами
                ломаной функция линейна.
                Линейная функция на
                отрезке либо возрастает,
                либо убывает, либо
                постоянна. Во всех
                случаях наибольшее значение
                достигается на одном
                из концов этого
                участка. Разделив исследуемый
                отрезок внутренними вершинами,
                получаем несколько таких
                линейных участков.
                Поэтому достаточно проверить
                все внутренние вершины
                и два конца самого исследуемого отрезка. Перебирать бесконечно много
                промежуточных аргументов не нужно. Горизонтальный участок может давать
                одинаковый максимум в нескольких точках, но вопрос о значении остаётся
                однозначным. Число точек достижения максимума и само максимальное
                значение — разные характеристики.
            """),
            _section("Находим значение внутри звена ломаной", """
                Граница исследуемого отрезка
                может не совпадать
                с вершиной. Тогда
                её ординату нужно
                вычислить по линейности
                соответствующего звена.
                Определите, какую долю
                горизонтального расстояния между
                соседними вершинами прошли
                до нужной абсциссы.
                Умножьте эту долю
                на изменение ординаты
                и прибавьте ординату
                начальной вершины.
                Полученное значение лежит
                между ординатами концов звена. Если доля отрицательна или больше единицы,
                выбран не тот участок. Сохраняйте дробь точно, даже если она
                не имеет конечной десятичной записи: промежуточная величина не обязана
                быть удобным десятичным числом. Для сравнения дробей можно использовать
                общий знаменатель.
            """, r"f(x)=y_1+\frac{x-x_1}{x_2-x_1}(y_2-y_1)"),
            _section("Сравниваем значения, а не внешнюю форму", """
                Выпишите список допустимых
                аргументов-кандидатов и напротив
                каждого его ординату.
                Затем выберите наибольшую
                ординату по обычному
                порядку чисел.
                При отрицательных значениях
                более высокому положению
                соответствует число ближе
                к нулю, а
                не число с
                большим модулем.
                Проверьте, что список
                содержит обе границы
                и все внутренние вершины,
                но не включает внешние. В ответ записывается максимальное значение,
                а не аргумент, где оно достигается. Дополнительно можно проследить
                направление изменения на каждом звене: это подтверждает, что внутри
                линейного участка не пропущена более высокая точка. При наличии равных
                максимумов достаточно одного общего числового значения без перечисления точек.
                Если граница попадает точно в вершину, её значение учитывают один раз:
                повторение одной точки в списке не создаёт нового кандидата или нового значения.
            """),
        ],
    },
})


_LESSONS.update({
    "successive-percentages": {
        "minutes": 5,
        "takeaway": "Каждый процент относится к своей текущей базе; последовательные "
                    "изменения задаются произведением множителей, а не суммой процентов.",
        "sections": [
            _section("Процент всегда относится к некоторой базе", """
                Один процент — одна
                сотая часть выбранной
                величины. Прежде чем
                считать изменение цены,
                назовите эту величину:
                первоначальная цена или
                цена после предыдущего
                изменения. При повышении
                к базе прибавляется
                её процентная часть,
                при скидке вычитается.
                Поэтому удобнее сразу
                записать новую цену
                как произведение старой
                на соответствующий множитель.
                Этот переход объединяет два действия в одно, но не меняет смысла процента.
                Повышение на одну пятую означает сохранение всей старой цены и добавление
                ещё одной пятой, а скидка на одну пятую оставляет четыре пятых.
                В каждом случае речь идёт о доле выбранной базы, а не о фиксированном числе рублей.
            """, r"P_{\text{нов}}=P\left(1+\frac{p}{100}\right)"),
            _section("Проводим цену через два периода", """
                Для первого месяца
                базой является первоначальная
                цена. После повышения
                получается новая сумма,
                которая становится базой
                скидки второго месяца.
                Запишите два последовательных
                состояния цены, чтобы
                не потерять этот
                переход. Можно сначала
                вычислить повышенную цену,
                затем размер скидки
                в рублях и
                окончательную цену.
                Можно сразу перемножить
                два процентных множителя с начальной ценой. Обе записи равносильны.
                Первая полезна для проверки базы скидки, вторая сокращает вычисления.
                Если промежуточная цена дробная, сохраните точное значение: округление
                изменило бы базу второго процента. В заданиях этого семейства все
                денежные результаты точно выражаются рублями и копейками
                без дополнительного правила округления.
            """, r"P_2=P_0\left(1+\frac p{100}\right)\left(1-\frac q{100}\right)"),
            _section("Почему одинаковые проценты не отменяются", """
                Повышение и скидка
                с одинаковым процентным
                числом действуют на
                разные базы.
                После повышения база
                скидки больше исходной,
                поэтому скидка в
                рублях превосходит прежнюю
                прибавку. Итоговая цена
                оказывается ниже первоначальной.
                Алгебра подтверждает это
                произведением суммы и
                разности единицы и
                одной доли: остаётся
                единица минус квадрат доли.
                Простое вычитание процентов потеряло бы этот дополнительный член.
                Если нужно узнать общее процентное изменение, сначала найдите
                отношение окончательной цены к первоначальной, затем вычтите единицу
                и переведите долю в проценты. Это другой вопрос, чем сама конечная
                цена, поэтому не подменяйте им ответ задачи о стоимости товара.
            """),
            _section("Проверяем деньги и допустимые множители", """
                Начальная цена положительна,
                повышение увеличивает её,
                а скидка меньше
                ста процентов сохраняет
                положительную окончательную цену.
                Сравните стоимость после
                скидки с повышенной:
                она должна быть
                меньше, независимо от
                того, выше или
                ниже она первоначальной.
                Проверьте отдельную денежную
                скидку умножением текущей
                базы на её
                процентную долю.
                Разность двух последовательных цен должна совпасть с этой суммой.
                Указанные периоды не означают начисление банковских процентов:
                здесь моделируется цена товара, меняющаяся в названные моменты.
                Отсутствие дополнительных сборов позволяет ограничиться двумя изменениями.
                В ответ записывайте окончательную цену в рублях, сохраняя копейки
                десятичной частью числа, если они появились в точном расчёте.
            """),
        ],
    },
    "capitalized-deposit": {
        "minutes": 5,
        "takeaway": "Проценты присоединяются в конце каждого полного года; каждый следующий "
                    "год работает новый остаток, а при закрытии возвращается весь вклад.",
        "sections": [
            _section("Рисуем календарь начислений", """
                Сумма внесена в
                начале срока одним
                платежом. До первого
                полного года начисления
                в нашей модели
                нет. В конце
                каждого года проценты
                добавляются к текущему
                остатку, после чего
                начинается следующий период.
                Такое присоединение процентов
                называется капитализацией.
                Годовая ставка применяется
                ровно один раз
                за полный год.
                Поэтому важно считать количество начислений, а не количество написанных
                на календарной линии отметок: начальный момент не является начислением.
                Если срок составляет несколько полных лет, число годовых начислений
                совпадает с числом этих лет. Закрытие происходит после последнего
                начисления, поэтому проценты последнего года включаются
                в выдаваемую вкладчику сумму.
            """),
            _section("Как меняется база процентов", """
                В первый год
                базой служит первоначальный
                взнос. Во второй
                год базой станет
                взнос вместе с
                присоединёнными процентами первого
                года. Далее правило
                повторяется. Прибавление процентов
                можно заменить умножением
                остатка на единицу
                плюс процентная доля.
                Один и тот
                же множитель применяется
                ко всё новым
                остаткам последовательно.
                Поэтому итог выражается степенью годового множителя. Использование первоначального
                взноса для каждого начисления описывало бы простые проценты без капитализации,
                то есть другой договор. Здесь прирост в рублях растёт по годам,
                хотя сама процентная ставка постоянна. Это различие между постоянной
                долей и постоянной денежной прибавкой принципиально для построения модели.
            """, r"B_i=B_{i-1}\left(1+\frac r{100}\right),\quad B_0=P"),
            _section("Считаем точно и различаем вклад с доходом", """
                Для короткого срока
                удобно составить список
                остатков после каждого
                года. Для общего
                выражения используйте степень
                годового множителя.
                Оба способа должны
                давать одинаковый результат.
                Не округляйте промежуточный
                остаток без указания
                договора: от него
                зависит следующее начисление.
                Числа этого семейства
                позволяют вести каждый
                период точно до копейки.
                Сумма при закрытии включает первоначальный капитал и весь начисленный
                доход. Если бы спрашивали только проценты, потребовалось бы вычесть
                первоначальный взнос из последнего остатка. В нашем вопросе вычитать
                ничего не нужно: вкладчик получает весь остаток после последнего начисления.
                Подпишите в черновике отдельно «остаток» и «доход», чтобы не смешать эти величины.
            """, r"B_n=P\left(1+\frac r{100}\right)^n"),
            _section("Контроль денежного баланса", """
                Разность соседних остатков
                должна равняться ставке,
                умноженной на предыдущий
                остаток. Проверяя каждую
                такую разность, можно
                обнаружить пропущенный период
                или неверную базу.
                Сумма всех начислений
                вместе с первоначальным
                взносом должна совпасть
                с выдаваемой суммой.
                При положительной ставке
                остатки возрастают, а
                итог больше внесённого
                капитала.
                Условия об отсутствии пополнений, снятий, налогов и комиссий существенны:
                каждое дополнительное движение денег изменило бы остаток или выдачу.
                Они явно исключены, поэтому степенная модель полностью описывает
                указанный договор. После закрытия остаток самого вклада становится
                нулевым, а вся рассчитанная сумма переходит вкладчику; это завершает
                денежную цепочку и уточняет, в какой момент измеряется ответ.
            """),
        ],
    },
    "paid-interest-deposit": {
        "minutes": 5,
        "takeaway": "При выплате процентов база вклада не растёт: квартальный доход "
                    "равен P·r/400, взнос возвращается отдельно после последней выплаты.",
        "sections": [
            _section("Проценты покидают вклад", """
                Не каждый вклад
                увеличивается после начисления
                процентов. По этому
                договору начисленные деньги
                сразу переводятся на
                отдельный счёт, который
                сам процентов не
                приносит. На исходном
                вкладе остаётся только
                первоначальный взнос.
                Поэтому следующий период
                начинается с той
                же процентной базой,
                что и предыдущий.
                Это вклад с выплатой
                дохода, а не с капитализацией. Разница определяется не словом
                «начислить», а дальнейшей судьбой начисленных денег. Нарисуйте два
                счета: постоянный основной вклад и отдельный накопитель выплаченных
                процентов. Такое представление помогает не приписывать доходу повторное
                начисление и отделить возврат капитала от выплаты заработанных процентов.
            """),
            _section("Согласуем годовую ставку с кварталом", """
                В году четыре
                квартала. Условие прямо
                задаёт простое правило:
                за каждый полный
                квартал выплачивается четверть
                годовой ставки от
                первоначального взноса.
                Сначала переведите процент
                в долю делением
                на сто, затем
                разделите её на
                четыре. Получается делитель
                четыреста для годового
                процентного числа.
                Это правило установлено
                договором задачи, а не универсально для любого банковского продукта.
                При другой периодичности или эффективной годовой ставке пересчёт
                мог бы отличаться. Здесь срок уже выражен числом полных
                кварталов, поэтому дополнительного подсчёта дней и неполных месяцев
                нет. Единицы ставки и число периодов согласуются до суммирования денежных выплат.
            """, r"I_{\text{квартал}}=P\frac{r}{400}"),
            _section("Складываем выплаты и отдельно возвращаем взнос", """
                Размер каждой квартальной
                выплаты одинаков, поскольку
                и ставка, и
                база постоянны.
                Общий процентный доход
                равен одной выплате,
                умноженной на число
                кварталов. Последняя выплата
                также входит в
                сумму: после неё
                происходит возврат основного
                вклада. Возврат взноса
                не является заработанным
                доходом, это передача
                собственных первоначальных денег.
                Поэтому при вопросе о процентах его не прибавляют к ответу.
                Если нужно проверить все поступления, сложите доход и возвращённый
                взнос отдельно. На беспроцентном счёте проценты могут накапливаться,
                но простое накопление выплат не превращается в капитализацию:
                на эти средства не начисляется дополнительный доход ни на одном этапе модели.
            """),
            _section("Проверка по полной временной линии", """
                На начальной отметке
                вкладчик перечисляет основной
                взнос. Затем на
                каждой квартальной отметке
                получает одну процентную
                выплату. На последней
                отметке получает и
                проценты, и возврат
                всей основной суммы.
                После этого основной
                вклад закрыт, его
                остаток равен нулю.
                Проверьте, что число
                процентных поступлений совпадает
                со сроком в кварталах.
                При удвоении количества полных кварталов доход в этой модели
                удваивается, что отличает её от сложного роста с капитализацией.
                При положительных ставке и взносе доход положителен. Вычисления
                сохраняйте точными: параметры подобраны так, что выплаты выражаются
                рублями и копейками без округления. Прочитайте вопрос ещё раз:
                требуется сумма процентов за весь срок, а не одна квартальная выплата.
            """),
        ],
    },
    "equal-principal-credit": {
        "minutes": 6,
        "takeaway": "Равны доли основного долга; проценты начисляются до очередного платежа "
                    "на уменьшающийся остаток. Полная выплата — основной долг плюс все проценты.",
        "sections": [
            _section("Равные доли долга не означают равные платежи", """
                Заёмщик получает кредит
                одной суммой. Договор
                требует ежегодно возвращать
                одинаковую долю первоначального
                основного долга.
                Кроме этой доли,
                в каждом платеже
                присутствуют проценты за
                прошедший год.
                Поэтому полный платёж
                состоит из двух
                частей, и одинаковой
                является только первая.
                Основной долг постепенно
                уменьшается, вслед за ним
                уменьшаются годовые проценты и полные платежи. Если перепутать
                этот договор с равными полными платежами, получится другая
                финансовая модель. Начните решение с деления первоначальной суммы
                на число лет: это фиксированная ежегодная часть основного долга,
                которая позволит восстановить все остатки без подбора размера
                каждого платежа отдельно.
            """),
            _section("Порядок начисления и выплаты", """
                В начале первого
                года долг равен
                всей полученной сумме.
                В конце года
                сначала начисляются проценты
                на этот остаток,
                затем выплачиваются все
                проценты и очередная
                доля основного долга.
                Во втором году
                процентная база уже
                меньше на одну
                возвращённую долю.
                После последнего платежа
                долг становится нулевым.
                Не уменьшайте базу текущего года до начисления его процентов:
                это означало бы платёж в начале года и другой порядок
                операций. Удобная таблица имеет колонки «долг до начисления»,
                «проценты», «основная часть», «долг после платежа». Последний
                столбец каждой строки становится первой колонкой следующей,
                обеспечивая непрерывность расчёта.
            """),
            _section("Сумма процентов через ряд остатков", """
                До годовых начислений
                долги образуют убывающую
                арифметическую прогрессию:
                весь кредит, кредит
                без одной доли
                и так далее
                до одной последней
                доли. Проценты каждого
                года равны одному
                и тому же
                проценту соответствующего остатка.
                Поэтому сначала можно
                сложить остатки, затем
                умножить сумму на
                процентную долю.
                Сумма арифметической прогрессии равна полусумме первого и последнего
                членов, умноженной на их количество. Число членов равно числу
                лет, а нулевой остаток после погашения в сумму не входит:
                на него уже не начисляются проценты. Общая выплата получается
                прибавлением всех процентов к первоначальному основному долгу,
                который возвращается целиком.
            """, r"I=\frac r{100}\left(P+\left(P-\frac Pn\right)+\cdots+\frac Pn\right)"),
            _section("Проверяем погашение и общую сумму", """
                Сумма всех основных
                частей должна точно
                равняться кредиту.
                В последнем году
                до начисления остаётся
                одна основная часть,
                поэтому последний платёж
                возвращает её и
                проценты на неё.
                Дальнейшего долга не
                остаётся. Проверьте, что
                полные платежи убывают,
                поскольку процентная ставка
                положительна, а база
                становится меньше ежегодно.
                Общая выплата обязана превышать первоначальный кредит ровно на
                сумму процентов. Нельзя начислить годовую ставку на первоначальную
                сумму и умножить на число лет: так была бы проигнорирована
                амортизация долга. В этом семействе нет комиссий, налогов
                и досрочных внеплановых платежей. Все денежные части представлены
                точно, поэтому дополнительного перерасчёта или округлённого последнего
                платежа не требуется.
            """),
        ],
    },
    "equal-payment-credit": {
        "minutes": 6,
        "takeaway": "Запишите два остатка B₁ = Pq − A и B₂ = qB₁ − A; "
                    "условие B₂ = 0 определяет одинаковый полный платёж.",
        "sections": [
            _section("Что именно одинаково в договоре", """
                Кредит погашается двумя
                одинаковыми полными платежами
                в конце двух
                последовательных лет.
                Одинаковым является весь
                платёж, включающий и
                проценты, и возвращаемую
                часть основного долга.
                Эти части по
                годам различаются.
                После первого платежа
                долг меньше первоначального,
                поэтому процентов второго
                года начисляется меньше,
                а на возврат основного
                долга из того же платежа остаётся больше. Нельзя заранее
                делить основной долг пополам и прибавлять проценты: такой
                расчёт относился бы к равным основным частям, а не
                к равным полным платежам. Обозначьте неизвестным именно полный
                годовой платёж и последовательно проследите оба остатка долга по договору.
            """),
            _section("Первый год: проценты перед платежом", """
                Пусть годовой множитель
                равен единице плюс
                процентная ставка,
                выраженная долей.
                В конце первого
                года первоначальный долг
                умножается на этот
                множитель. Затем из
                увеличенного долга вычитается
                первый платёж.
                Получившееся число —
                остаток после платежа,
                а не сумма
                процентов за год.
                Именно этот остаток
                становится базой следующего начисления. Если вместо него снова
                взять первоначальный кредит, будет проигнорировано частичное погашение.
                Если вычесть платёж до умножения, проценты окажутся начислены
                уже на уменьшенную сумму, что противоречит установленному порядку.
                Скобки в записи следующего года фиксируют обе операции первого года целиком,
                поэтому их нельзя пропускать при умножении остатка на годовой множитель.
            """, r"B_1=Pq-A,\qquad q=1+\frac r{100}"),
            _section("Последний год задаёт уравнение", """
                Во втором году
                остаток первого года
                снова увеличивается
                на проценты.
                Из него вычитается
                такой же полный
                платёж. По условию
                кредит погашен полностью,
                значит новый остаток
                равен нулю.
                Подставьте выражение первого
                остатка, раскройте скобки
                и соберите оба
                слагаемых с платежом.
                Получится линейное уравнение
                относительно размера платежа, хотя в коэффициентах присутствует квадрат
                годового множителя. Одна часть первого платежа уже уменьшила
                базу второго начисления, поэтому при раскрытии скобок первый
                платёж тоже умножается на годовой множитель. Этот член
                отличает верную модель от ошибочного деления долга с двухлетними процентами на два.
            """, r"(Pq-A)q-A=0\quad\Longrightarrow\quad A=\frac{Pq^2}{q+1}"),
            _section("Проверка двух платежей и денежного баланса", """
                Рассчитайте первый остаток
                по найденному платежу.
                Он должен быть
                положителен: кредит ещё
                не закрыт.
                Начислите на него
                проценты второго года
                и убедитесь, что
                полученная задолженность точно
                совпадает со вторым
                платежом. После вычитания
                должен получиться нуль,
                без остатка или
                переплаты.
                Дополнительно сложите проценты
                двух лет: удвоенный платёж должен равняться первоначальному кредиту
                плюс эта сумма. Так проверяется весь поток денег.
                Условия явно исключают комиссии, налоги и иные платежи,
                поэтому в баланс не добавляются неизвестные суммы. Параметры
                подобраны для точных расчётов до копейки. Ответ относится
                к одному платежу, а не к общей сумме двух платежей или процентной переплате.
            """),
        ],
    },
    "family-budget": {
        "minutes": 5,
        "takeaway": "Резерв считайте от указанной базы дохода; свободные деньги равны "
                    "доходу минус обязательные расходы и перевод в резерв.",
        "sections": [
            _section("Один период и одна граница бюджета", """
                Бюджет объединяет денежные
                поступления и направления
                использования денег за
                один период.
                В этом семействе
                все суммы относятся
                к одному календарному
                месяцу, а доход
                дан уже после
                налогов. Поэтому повторно
                вычитать налог или
                переводить годовые суммы
                в месячные не
                требуется. Начальный свободный
                остаток равен нулю.
                Сначала найдите границы расчёта: какие деньги поступили в этом
                месяце и какие расходы обязательны в нём. Если бы
                присутствовали долги, прежние накопления или иные поступления, их
                пришлось бы явно включить в модель. Условие исключает
                такие дополнительные потоки, позволяя описать весь доступный
                месячный доход одной строкой.
            """),
            _section("Расходы и перевод в резерв", """
                Обязательные расходы уходят
                на оплату жилья,
                питания и транспорта.
                Перевод в резерв
                имеет другой экономический
                смысл: деньги остаются
                собственностью семьи,
                но отделяются от
                средств для текущих
                покупок. Поэтому для
                вопроса о свободной
                сумме резерв нужно
                вычесть вместе с
                обязательными расходами,
                хотя общие активы семьи
                от самого перевода не уменьшаются. Полезно нарисовать два
                кармана: деньги на текущем счёте и деньги в резерве.
                Оплата обязательных покупок уменьшает общий запас, перевод между
                карманами лишь меняет его расположение. Такое различие помогает
                не назвать весь остаток после расходов доступным для дополнительных покупок,
                если часть
                этого остатка по условию уже зарезервирована и расходоваться сейчас не должна.
            """),
            _section("От какого числа берётся процент резерва", """
                В условии сказано,
                что доля резерва
                считается от всего
                месячного дохода.
                Следовательно, сначала умножьте
                именно доход на
                процентную долю,
                независимо от размера
                обязательных расходов.
                Если бы резерв
                считали от остатка
                после расходов,
                получилась бы другая
                сумма и другая
                модель бюджета.
                Переведите процент в дробь делением на сто, вычислите резерв,
                затем сложите три обязательные статьи в рублях. Процентное
                число само по себе нельзя прибавлять к рублёвым расходам:
                сначала оно должно превратиться в денежную сумму с указанной
                базой. Когда все направления выражены в одной валюте за
                один месяц, их можно вычесть из дохода в любом арифметическом порядке
                без изменения результата.
            """, r"R=Y\frac p{100},\qquad S=Y-H-F-T-R"),
            _section("Проверяем разложение дохода", """
                Сложите свободные деньги,
                резерв и обязательные
                расходы. Должен восстановиться
                весь месячный доход.
                Это основной денежный
                баланс, который выявляет
                пропущенную статью или
                повторное вычитание.
                Свободная сумма может
                в других задачах
                оказаться отрицательной:
                тогда план расходов
                превышает возможности бюджета
                и образуется дефицит.
                В наших условиях
                выбран положительный остаток, поэтому дополнительных источников финансирования
                не требуется. Если доля резерва увеличивается при прежних
                доходе и расходах, доступные деньги должны уменьшаться.
                Если уменьшается одна обязательная статья, свободная сумма
                возрастает на ту же величину. Эти простые изменения
                проверяют знаки формулы. Ответ показывает ресурс для остальных
                покупок, а не весь денежный запас семьи вместе с резервным счётом
                после завершения месяца.
            """),
        ],
    },
    "tariff-threshold": {
        "minutes": 6,
        "takeaway": "Сравнивайте полные месячные стоимости; для строгого неравенства "
                    "выбирается наименьшее целое значение выше границы равенства.",
        "sections": [
            _section("Фиксированная плата и цена единицы", """
                Тариф может содержать
                две разные части:
                постоянную плату за
                период и стоимость
                каждой использованной единицы.
                Более низкая цена
                единицы не гарантирует
                меньший месячный счёт,
                если присутствует дополнительная
                постоянная плата.
                При малом потреблении
                она может перевесить
                всю экономию,
                а при большом
                потреблении окупиться.
                Поэтому сравнивают не отдельные ставки, а полные стоимости
                при одном и том же объёме за один месяц.
                Обозначьте потребление неизвестным числом. В первом тарифе
                стоимость пропорциональна ему. Во втором к пропорциональной
                части прибавляется фиксированная сумма, которая уплачивается один раз за месяц,
                а не умножается на количество использованных киловатт-часов.
            """),
            _section("Строим строгое неравенство стоимости", """
                Слова «второй строго
                дешевле» означают,
                что его полная
                стоимость должна быть
                меньше первой,
                а не просто
                не больше.
                Запишите обе стоимости
                и поставьте нужный
                знак неравенства.
                После переноса переменных
                частей фиксированная плата
                сравнивается с экономией
                на каждой единице,
                умноженной на объём.
                Разность удельных ставок положительна, поскольку второй тариф
                имеет меньшую цену единицы. Деление на эту разность
                сохраняет направление неравенства. Полученная граница соответствует
                равенству месячных счетов. В точке равенства второй тариф
                ещё не даёт строгой выгоды, поэтому ответ должен
                лежать выше этой границы, а не совпадать с ней без проверки формулировки.
            """, r"F+bx<ax\quad\Longleftrightarrow\quad x>\frac{F}{a-b},\qquad a>b"),
            _section("Целое потребление и выбор первого значения", """
                Условие разрешает только
                неотрицательные целые количества
                киловатт-часов. После решения
                неравенства на числовой
                прямой нужно выбрать
                первое допустимое целое
                значение. Если граница
                целая, её необходимо
                увеличить на единицу,
                потому что равенство
                не подходит.
                Если граница дробная,
                подходит ближайшее целое
                число строго выше неё.
                Это не приблизительное округление
                математического ответа, а точный отбор из дискретного множества,
                явно указанного условием. Округление к ближайшему целому могло
                бы выбрать число ниже границы и нарушить неравенство.
                Сначала сохраняйте границу точной дробью, затем сравнивайте с
                целыми числами. Такой порядок работает независимо от того,
                является ли десятичная запись промежуточной границы конечной или бесконечной.
            """),
            _section("Две соседние проверки доказывают минимум", """
                Подставьте выбранный объём
                в обе стоимости.
                Вторая должна оказаться
                строго меньше первой.
                Затем проверьте предыдущее
                целое значение:
                при нём строгой
                выгоды быть не
                должно. Поскольку экономия
                возрастает линейно с
                положительным наклоном,
                эти две проверки
                подтверждают наименьший
                допустимый объём,
                а не просто один выгодный.
                Условие о неизменных ставках на весь объём существенно:
                при ступенчатых тарифах пришлось бы разделять диапазоны потребления.
                Здесь лимитов и дополнительных сборов нет, поэтому обе
                линейные стоимости действуют для всех рассматриваемых значений.
                Результат записывается в единицах потребления, не в рублях
                экономии. Денежную разность можно использовать для проверки, но
                она не заменяет ответ на вопрос о первом выгодном целом объёме.
            """),
        ],
    },
})


def build_lessons(profile: ProfileSource) -> list[dict]:
    """One substantive lesson per family; worked seed differs from practice 0, 1, 2."""
    lessons = []
    for family in FAMILIES:
        content = _LESSONS[family.id]
        worked = family.generate(149, profile)
        rows = "\n".join(f"{name} = {value} ({unit})"
                         for name, value, unit in worked["table"]["rows"])
        lessons.append({
            "id": f"course-{family.id}", "title": family.title, "slot": family.slot,
            "minutes": content["minutes"], "skill_ids": list(family.skill_ids),
            "sections": [dict(section) for section in content["sections"]],
            "example": {"statement": worked["statement"] + "\nДанные:\n" + rows,
                        "steps": list(worked["solution"]), "answer": worked["answer"]},
            "takeaway": content["takeaway"], "family_ids": [family.id],
            "practice_task_ids": [f"course-{family.id}-{seed}" for seed in range(3)],
        })
    return lessons
