"""Authored draft families for distributions, algebra and calculus (slots 6–9).

All grading arithmetic is rational. Figure coordinates alone may use floats.
Human review metadata is supplied, unset, by the shared task constructor.
"""

from copy import deepcopy
from fractions import Fraction

from app.generators.base import Family, decimal_text, make_task
from app.schemas import ProfileSource


def _seed(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 2**32 - 1:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    return value


def _task(family_id: str, seed: int, profile: ProfileSource, **fields) -> dict:
    family = _CATALOG[family_id]
    return make_task(
        profile, family.slot, family_id, seed,
        title=family.title, skills=list(family.skill_ids), **fields,
    )


def _distribution(seed: int) -> tuple[tuple[int, Fraction], ...]:
    first = 2 + seed % 40
    second = first + 2 + (seed // 40) % 5
    third = second + 3 + (seed // 200) % 5
    p = Fraction(2 + (seed // 1000) % 3, 10)
    q = Fraction(3 + (seed // 3000) % 2, 10)
    return ((first, p), (second, q), (third, 1 - p - q))


def _table(rows: tuple[tuple[int, Fraction], ...]) -> dict:
    return {
        "headers": ["Значение X", "Вероятность"],
        "rows": [[str(x), decimal_text(p)] for x, p in rows],
    }


def _weighted_mean(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    rows = _distribution(seed)
    answer = sum((x * p for x, p in rows), Fraction())
    terms = " + ".join(f"{x} · {decimal_text(p)}" for x, p in rows)
    return _task(
        "distribution-weighted-mean", seed, profile,
        statement=("Случайная величина X — число баллов за случайный приз. "
                   "Её распределение дано в таблице. Найдите математическое ожидание X."),
        answer=answer, table=_table(rows), formula=r"M(X)=\sum_i x_i p_i",
        hints=[
            "Значения имеют разные вероятности: нужно среднее с весами.",
            "Математическое ожидание равно сумме произведений xᵢpᵢ.",
            f"Сложите {terms}; каждую строку таблицы используйте один раз.",
        ],
        solution=[
            "Вероятности неотрицательны и в сумме равны 1; таблица нормирована.",
            f"M(X) = {terms} = {decimal_text(answer)}.",
            f"Полученное среднее лежит между {rows[0][0]} и {rows[-1][0]} баллами.",
        ],
    )


def _missing_probability(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    first = 1 + seed % 50
    p = Fraction(1 + seed % 7, 10)
    q = Fraction(1 + (seed // 7) % 2, 10)
    answer = 1 - p - q
    return _task(
        "distribution-missing-probability", seed, profile,
        statement=("В таблице перечислены все возможные значения случайной величины X. "
                   "Найдите пропущенную вероятность p."),
        table={"headers": ["Значение X", "Вероятность"], "rows": [
            [str(first), decimal_text(p)], [str(first + 1), "p"],
            [str(first + 3), decimal_text(q)],
        ]},
        answer=answer,
        hints=[
            "Все возможные значения образуют полную группу исходов.",
            "Сумма вероятностей всех строк должна равняться единице.",
            f"Вычтите из 1 известные вероятности {decimal_text(p)} и {decimal_text(q)}.",
        ],
        solution=[
            f"{decimal_text(p)} + p + {decimal_text(q)} = 1.",
            f"p = 1 − {decimal_text(p)} − {decimal_text(q)} = {decimal_text(answer)}.",
            "Все три вероятности положительны, а их сумма равна 1.",
        ],
    )


def _weighted_variance(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    rows = _distribution(seed)
    mean = sum((x * p for x, p in rows), Fraction())
    second = sum((x * x * p for x, p in rows), Fraction())
    answer = second - mean * mean
    mean_terms = " + ".join(f"{x} · {decimal_text(p)}" for x, p in rows)
    second_terms = " + ".join(f"{x}² · {decimal_text(p)}" for x, p in rows)
    return _task(
        "distribution-weighted-variance", seed, profile,
        statement=("Случайная величина X — число баллов за случайный приз. "
                   "Её распределение дано в таблице. Найдите дисперсию X."),
        answer=answer, table=_table(rows), formula=r"D(X)=M(X^2)-(M(X))^2",
        difficulty=2, estimated_seconds=180,
        hints=[
            "Дисперсия измеряет разброс относительно среднего, а не само среднее.",
            "Найдите M(X) и M(X²), затем вычислите M(X²) − (M(X))².",
            f"Для второго момента сложите {second_terms}; вероятности не возводятся в квадрат.",
        ],
        solution=[
            "Вероятности таблицы в сумме дают 1.",
            f"M(X) = {mean_terms} = {decimal_text(mean)}.",
            f"M(X²) = {second_terms} = {decimal_text(second)}.",
            f"D(X) = {decimal_text(second)} − ({decimal_text(mean)})² "
            f"= {decimal_text(answer)}. Дисперсия неотрицательна.",
        ],
    )


def _two_point_deviation(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    center = 5 + seed % 40
    radius = 1 + (seed // 40) % 4
    left, right = center - radius, center + radius
    return _task(
        "distribution-two-point-deviation", seed, profile,
        statement=("Распределение случайной величины X дано в таблице. "
                   "Найдите стандартное отклонение X."),
        table=_table(((left, Fraction(1, 2)), (right, Fraction(1, 2)))),
        answer=radius, formula=r"\sigma(X)=\sqrt{D(X)}", difficulty=2,
        hints=[
            "Сначала найдите среднее, затем средний квадрат отклонения от него.",
            "Стандартное отклонение — неотрицательный квадратный корень из дисперсии.",
            f"Среднее равно ({left} + {right})/2. Найдите расстояние каждого исхода до него.",
        ],
        solution=[
            f"M(X) = ({left} + {right})/2 = {center}.",
            f"D(X) = ({left} − {center})² · 0,5 + "
            f"({right} − {center})² · 0,5 = {radius * radius}.",
            f"σ(X) = √{radius * radius} = {radius}. Отрицательный корень не подходит.",
        ],
    )


def _step_cdf(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    rows = _distribution(seed)
    threshold = rows[1][0]
    answer = rows[0][1] + rows[1][1]
    return _task(
        "distribution-step-cdf", seed, profile,
        statement=("Распределение X дано в таблице. Функция распределения определена как "
                   f"F(t) = P(X ≤ t). Найдите F({threshold})."),
        answer=answer, table=_table(rows), formula=r"F(t)=P(X\leq t)",
        hints=[
            "Нужно накопить вероятности значений, не превосходящих порог.",
            "В определении стоит знак ≤, поэтому равенство порогу тоже учитывается.",
            f"Выберите строки X = {rows[0][0]} и X = {threshold} и сложите их вероятности.",
        ],
        solution=[
            f"Событие X ≤ {threshold} включает значения {rows[0][0]} и {threshold}.",
            f"F({threshold}) = {decimal_text(rows[0][1])} + "
            f"{decimal_text(rows[1][1])} = {decimal_text(answer)}.",
            f"Вероятность значения {rows[2][0]} не входит в эту сумму.",
        ],
    )


def _linear_density(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    right = 2 ** (1 + seed % 5) * 5 ** ((seed // 5) % 2)
    answer = Fraction(2, right * right)
    return _task(
        "distribution-linear-density", seed, profile,
        statement=("Плотность непрерывной случайной величины равна f(x) = c·x при "
                   f"0 ≤ x ≤ {right} и равна нулю вне этого отрезка. Найдите c."),
        answer=answer, formula=r"\int_{-\infty}^{+\infty} f(x)\,dx=1",
        hints=[
            "Полная площадь под графиком плотности должна равняться 1.",
            "График на указанном отрезке ограничивает треугольник с высотой c·b.",
            f"Составьте равенство {right} · (c · {right})/2 = 1 и выразите c.",
        ],
        solution=[
            f"Основание треугольника равно {right}, высота равна {right}c.",
            f"Полная площадь: c · {right * right}/2 = 1.",
            f"c = 2/{right * right} = {decimal_text(answer)}. "
            "Коэффициент положителен, поэтому плотность неотрицательна.",
        ],
    )


def _uniform_interval(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    left = 1 + seed % 50
    width = 20 * (1 + (seed // 50) % 5)
    right = left + width
    start = left + (width // 10) * (1 + seed % 3)
    end = left + (width // 10) * (5 + (seed // 3) % 4)
    answer = Fraction(end - start, width)
    return _task(
        "distribution-uniform-interval", seed, profile,
        statement=(f"X равномерно распределена на отрезке [{left}; {right}]. "
                   f"Найдите P({start} ≤ X ≤ {end})."),
        answer=answer, formula=r"P(c\leq X\leq d)=\frac{d-c}{b-a}",
        hints=[
            "При равномерном распределении вероятность пропорциональна длине участка.",
            "Разделите длину нужного интервала на длину всего отрезка распределения.",
            f"Вычислите ({end} − {start})/({right} − {left}).",
        ],
        solution=[
            f"Весь отрезок имеет длину {right} − {left} = {width}.",
            f"Нужный участок целиком внутри него и имеет длину {end} − {start} = {end - start}.",
            f"Вероятность равна {end - start}/{width} = {decimal_text(answer)}. "
            "Для непрерывного распределения включение отдельных концов её не меняет.",
        ],
    )


def _exponential_survival(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    rate = 1 + (seed // 10) % 8
    logarithm = 2 ** (1 + seed % 5) * 5 ** ((seed // 5) % 2)
    answer = Fraction(1, logarithm)
    return _task(
        "distribution-exponential-survival", seed, profile,
        statement=("Время ожидания T имеет показательное распределение с интенсивностью "
                   f"λ = {rate} мин⁻¹. Найдите P(T > ln({logarithm})/{rate}), "
                   "где время измерено в минутах."),
        answer=answer, formula=r"F_T(t)=1-e^{-\lambda t},\quad t\geq0",
        hints=[
            "Событие означает, что ожидание ещё продолжается после указанного времени.",
            "Хвостовая вероятность равна 1 − F(t) = e^(−λt) при t ≥ 0.",
            f"Подставьте время: λt = ln({logarithm}); используйте e^(ln a) = a.",
        ],
        solution=[
            f"λ = {rate} > 0, t = ln({logarithm})/{rate} > 0.",
            f"P(T > t) = e^(−{rate} · ln({logarithm})/{rate}) = e^(−ln({logarithm})).",
            f"Это 1/{logarithm} = {decimal_text(answer)} точно, без вычисления логарифма.",
        ],
    )


def _normal_symmetry(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    center = 10 + seed % 70
    distance = 1 + (seed // 70) % 9
    left, right = center - distance, center + distance
    central = Fraction(50 + seed % 40, 100)
    answer = (1 - central) / 2
    return _task(
        "distribution-normal-symmetry", seed, profile,
        statement=("X имеет нормальное распределение с математическим ожиданием "
                   f"μ = {center}. Известно точное значение "
                   f"P({left} < X < {right}) = {decimal_text(central)}. "
                   f"Найдите P(X ≥ {right})."),
        answer=answer,
        hints=[
            "Нормальное распределение симметрично относительно своего среднего.",
            "За пределами симметричного интервала остаются два равновероятных хвоста.",
            f"Вычтите {decimal_text(central)} из 1 и разделите остаток на 2.",
        ],
        solution=[
            f"Границы {left} и {right} равноудалены от среднего {center} на {distance}.",
            f"Суммарная вероятность двух хвостов равна 1 − {decimal_text(central)} "
            f"= {decimal_text(1 - central)}.",
            f"Правый хвост: {decimal_text(1 - central)}/2 = {decimal_text(answer)}.",
            "Вероятность отдельной точки равна нулю. Использовано точное данное условия, "
            "а не приближённая таблица нормального распределения.",
        ],
    )


def _rational_excluded_root(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    excluded = 1 + seed % 30
    answer = excluded + 2 + (seed // 30) % 10
    total, product = excluded + answer, excluded * answer
    return _task(
        "rational-excluded-root", seed, profile,
        statement=(f"Решите уравнение (x² − {total}x + {product})/(x − {excluded}) = 0."),
        formula=rf"\frac{{x^2-{total}x+{product}}}{{x-{excluded}}}=0", answer=answer,
        hints=[
            "Дробь равна нулю, когда числитель равен нулю, а знаменатель не равен нулю.",
            f"Сначала запишите ограничение x ≠ {excluded}, затем разложите числитель.",
            f"Подберите два числа с суммой {total} и произведением {product}.",
        ],
        solution=[
            f"ОДЗ: x ≠ {excluded}.",
            f"Числитель равен (x − {excluded})(x − {answer}); "
            f"его нули: {excluded} и {answer}.",
            f"Значение {excluded} запрещено знаменателем. Остаётся x = {answer}.",
            f"При x = {answer} числитель равен 0, знаменатель равен {answer - excluded} ≠ 0.",
        ],
    )


def _radical_extraneous_root(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    shift = 1 + seed % 20
    difference = shift + 2 + (seed // 20) % 5
    constant = difference * difference - shift - difference
    answer = shift + difference
    rejected = shift + 1 - difference
    return _task(
        "radical-extraneous-root", seed, profile,
        statement=f"Решите уравнение √(x + {constant}) = x − {shift}.",
        formula=rf"\sqrt{{x+{constant}}}=x-{shift}", answer=answer, difficulty=2,
        hints=[
            "Арифметический квадратный корень всегда неотрицателен.",
            f"Требуются x + {constant} ≥ 0 и x ≥ {shift}; после этого возведите части в квадрат.",
            f"Решите x + {constant} = (x − {shift})² и проверьте обе найденные кандидатуры.",
        ],
        solution=[
            f"Необходимо x + {constant} ≥ 0 и x − {shift} ≥ 0; вместе это x ≥ {shift}.",
            f"После возведения в квадрат: x + {constant} = (x − {shift})².",
            f"Квадратное уравнение имеет корни {rejected} и {answer}.",
            f"Число {rejected} < {shift} даёт отрицательную правую часть и не подходит.",
            f"При x = {answer}: √({answer} + {constant}) = {difference}, "
            f"{answer} − {shift} = {difference}. Ответ: {answer}.",
        ],
    )


def _exponential_common_base(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    base = (2, 3, 5)[(seed // 30) % 3]
    shift = 1 + seed % 30
    exponent = 1 + (seed // 90) % 5
    answer = Fraction(shift + 2 * exponent, 2)
    return _task(
        "exponential-common-base", seed, profile,
        statement=(f"Решите уравнение {base}^(2x − {shift}) = {base * base}^{exponent}."),
        formula=rf"{base}^{{2x-{shift}}}={base * base}^{{{exponent}}}", answer=answer,
        hints=[
            "Представьте обе части как степени одного и того же числа.",
            f"Используйте {base * base} = {base}² и свойство (aᵐ)ⁿ = aᵐⁿ.",
            f"Основание {base} больше 1, поэтому можно приравнять показатели: "
            f"2x − {shift} = {2 * exponent}.",
        ],
        solution=[
            f"{base * base}^{exponent} = {base}^{2 * exponent}.",
            f"Функция {base}^t строго возрастает, значит 2x − {shift} = {2 * exponent}.",
            f"x = ({shift} + {2 * exponent})/2 = {decimal_text(answer)}.",
            f"При подстановке показатель слева равен {2 * exponent}, "
            "то есть исходные степени равны.",
        ],
    )


def _logarithmic_product_domain(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    shift = 1 + seed % 30
    answer = shift + 2 + (seed // 30) % 7
    number = answer * answer - shift * shift
    base = (2, 3, 5)[(seed // 210) % 3]
    return _task(
        "logarithmic-product-domain", seed, profile,
        statement=(f"Решите уравнение log_{base}(x − {shift}) + "
                   f"log_{base}(x + {shift}) = log_{base}({number})."),
        formula=(rf"\log_{{{base}}}(x-{shift})+\log_{{{base}}}(x+{shift})="
                 rf"\log_{{{base}}}({number})"), answer=answer, difficulty=2,
        hints=[
            "Оба аргумента логарифмов должны быть положительны.",
            "На ОДЗ объедините сумму логарифмов в логарифм произведения.",
            f"Решите (x − {shift})(x + {shift}) = {number}, "
            f"а затем оставьте только x > {shift}.",
        ],
        solution=[
            f"Основание {base} положительно и не равно 1. ОДЗ: x > {shift}.",
            f"По правилу суммы: log_{base}((x − {shift})(x + {shift})) = log_{base}({number}).",
            f"Аргументы равны: x² − {shift * shift} = {number}, то есть x² = {answer * answer}.",
            f"Кандидаты: x = −{answer} и x = {answer}. Только {answer} принадлежит ОДЗ.",
            f"Проверка: положительные аргументы {answer - shift} и {answer + shift} "
            f"имеют произведение {number}. Ответ: {answer}.",
        ],
    )


def _absolute_value_selected_root(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    shift = 20 + seed % 60
    distance = 1 + (seed // 60) % 9
    answer = shift - distance
    return _task(
        "absolute-value-selected-root", seed, profile,
        statement=(f"Решите уравнение |x − {shift}| = {distance}. "
                   "В ответе укажите меньший корень."),
        formula=rf"|x-{shift}|={distance}", answer=answer,
        hints=[
            "Модуль разности — расстояние на числовой прямой.",
            f"Искомые числа находятся по обе стороны от {shift} на расстоянии {distance}.",
            f"Решите x − {shift} = {distance} и x − {shift} = −{distance}; сравните корни.",
        ],
        solution=[
            f"Так как {distance} > 0, получаем два равенства: "
            f"x − {shift} = {distance} или x − {shift} = −{distance}.",
            f"Корни: {shift + distance} и {shift - distance}.",
            f"Меньший корень — {answer}. Его расстояние от {shift} равно {distance}.",
        ],
    )


def _power_product_quotient(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    base = 2 + seed % 20
    exponent = 2 + (seed // 20) % 4
    positive, negative = exponent + 2, 1 - exponent
    answer = base * base
    return _task(
        "power-product-quotient", seed, profile,
        statement=f"Вычислите ({base}^{positive} · {base}^({negative}))/{base}.",
        formula=rf"\frac{{{base}^{{{positive}}}\cdot {base}^{{{negative}}}}}{{{base}}}",
        answer=answer,
        hints=[
            "Не вычисляйте большие степени: у всех множителей одинаковое основание.",
            "При умножении показатели складываются, при делении — вычитаются.",
            f"Представьте знаменатель как {base}¹ и вычислите показатель "
            f"{positive} + ({negative}) − 1.",
        ],
        solution=[
            f"Основание {base} не равно нулю, поэтому отрицательная степень определена.",
            f"Общий показатель: {positive} + ({negative}) − 1 = 2.",
            f"Выражение равно {base}² = {answer} точно.",
        ],
    )


def _radical_conjugates(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    integer = 2 + seed % 40
    radicand = integer * integer + 1
    shift = 1 + (seed // 40) % 7
    answer = radicand - shift * shift
    return _task(
        "radical-conjugates", seed, profile,
        statement=f"Вычислите (√{radicand} + {shift})(√{radicand} − {shift}).",
        formula=rf"(\sqrt{{{radicand}}}+{shift})(\sqrt{{{radicand}}}-{shift})",
        answer=answer,
        hints=[
            "Множители отличаются только знаком между слагаемыми.",
            "Используйте (u + v)(u − v) = u² − v².",
            f"Возьмите u = √{radicand}, v = {shift}; квадрат корня равен подкоренному числу.",
        ],
        solution=[
            f"{radicand} > 0, поэтому квадратный корень определён.",
            f"По формуле разности квадратов: (√{radicand})² − {shift}² "
            f"= {radicand} − {shift * shift} = {answer}.",
            "Сам корень вычислять приближённо не требуется: смешанные произведения сокращаются.",
        ],
    )


def _rational_removable_factor(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    shift = 1 + seed % 50
    value = shift + 1 + (seed // 50) % 20
    answer = value + shift
    return _task(
        "rational-removable-factor", seed, profile,
        statement=(f"Найдите значение (x² − {shift * shift})/(x − {shift}) при x = {value}."),
        formula=rf"\frac{{x^2-{shift * shift}}}{{x-{shift}}},\quad x={value}",
        answer=answer,
        hints=[
            "До сокращения проверьте, что заданное значение не обращает знаменатель в ноль.",
            f"Разложите x² − {shift * shift} как (x − {shift})(x + {shift}).",
            f"При x ≠ {shift} общий множитель сокращается; подставьте {value} в x + {shift}.",
        ],
        solution=[
            f"x = {value} ≠ {shift}, значит исходная дробь определена.",
            f"Числитель: x² − {shift * shift} = (x − {shift})(x + {shift}).",
            f"На ОДЗ дробь равна x + {shift}; при заданном x это {value} + {shift} = {answer}.",
            f"Прямая проверка: ({value * value} − {shift * shift})/"
            f"({value} − {shift}) = {answer}.",
        ],
    )


def _logarithm_difference(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    base = 2 + seed % 9
    exponent = 2 + (seed // 9) % 3
    second = 3 + seed % 11
    first = base**exponent * second
    return _task(
        "logarithm-difference", seed, profile,
        statement=f"Вычислите log_{base}({first}) − log_{base}({second}).",
        formula=rf"\log_{{{base}}}({first})-\log_{{{base}}}({second})", answer=exponent,
        hints=[
            "Отдельные логарифмы могут быть неудобными, но их разность упрощается.",
            "При одинаковом основании разность логарифмов равна логарифму частного аргументов.",
            f"Разделите {first} на {second} и представьте результат как степень {base}.",
        ],
        solution=[
            f"Аргументы {first} и {second} положительны; основание {base} больше 1.",
            f"Разность равна log_{base}({first}/{second}) = log_{base}({base**exponent}).",
            f"Так как {base**exponent} = {base}^{exponent}, получаем {exponent}.",
        ],
    )


def _trigonometric_double_angle(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    opposite, adjacent, hypotenuse = (
        (3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (20, 21, 29),
    )[(seed // 20) % 5]
    multiplier = 1 + seed % 20
    coefficient = hypotenuse * hypotenuse * multiplier
    answer = -2 * opposite * adjacent * multiplier
    return _task(
        "trigonometric-double-angle", seed, profile,
        statement=(f"Найдите {coefficient}·sin(2α), если sin α = {opposite}/{hypotenuse} "
                   "и π/2 < α < π."),
        formula=r"\sin(2\alpha)=2\sin\alpha\cos\alpha", answer=answer, difficulty=2,
        hints=[
            "Для синуса двойного угла нужны и синус, и косинус исходного угла.",
            "Используйте cos²α = 1 − sin²α. Во второй четверти косинус отрицателен.",
            f"Получите cos α = −{adjacent}/{hypotenuse}, затем подставьте в 2 sin α cos α.",
        ],
        solution=[
            f"cos²α = 1 − ({opposite}/{hypotenuse})² = "
            f"{adjacent * adjacent}/{hypotenuse * hypotenuse}.",
            f"Угол во второй четверти, поэтому cos α = −{adjacent}/{hypotenuse}.",
            f"{coefficient} · sin(2α) = {coefficient} · 2 · {opposite}/{hypotenuse} "
            f"· (−{adjacent}/{hypotenuse}) = {answer}.",
            "Знак отрицателен: при π < 2α < 2π синус отрицателен.",
        ],
    )


def _coordinate(value: Fraction | int) -> int | float:
    value = Fraction(value)
    return value.numerator if value.denominator == 1 else float(value)


def _point(x: Fraction | int, y: Fraction | int) -> dict:
    return {"x": _coordinate(x), "y": _coordinate(y)}


def _figure(statement: str, lines: list, labels: list, *, dashed: int | None = None) -> dict:
    points = [point for line in lines for point in line]
    return {
        "description": statement,
        "x_min": _coordinate(min(0, *(x for x, _ in points)) - 1),
        "x_max": _coordinate(max(0, *(x for x, _ in points)) + 1),
        "y_min": _coordinate(min(0, *(y for _, y in points)) - 1),
        "y_max": _coordinate(max(0, *(y for _, y in points)) + 1),
        "axes": True,
        "lines": [
            {"points": [_point(x, y) for x, y in line], "dashed": index == dashed}
            for index, line in enumerate(lines)
        ],
        "circles": [],
        "labels": [{**_point(x, y), "text": name} for name, x, y in labels],
    }


def _vertices(points: list) -> str:
    return ", ".join(
        f"{name}({decimal_text(x)}; {decimal_text(y)})"
        for name, (x, y) in zip("ABCD", points, strict=False)
    )


def _vertex_labels(points: list) -> list:
    return [(name, x, y) for name, (x, y) in zip("ABCD", points, strict=False)]


def _piecewise_function_value(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    left = 1 + seed % 30
    width = 4 + 2 * ((seed // 30) % 5)
    bottom = 2 + (seed // 150) % 8
    top = bottom + 2 * (1 + (seed // 1200) % 5)
    points = [(left, bottom), (left + width, top), (left + 2 * width, bottom - 1)]
    argument = left + width // 2
    answer = Fraction(bottom + top, 2)
    statement = (f"График f — ломаная ABC с вершинами {_vertices(points)}. "
                 f"Найдите f({argument}). Координаты заданы точно.")
    return _task(
        "piecewise-function-value", seed, profile, statement=statement, answer=answer,
        figure=_figure(statement, [points], _vertex_labels(points)),
        hints=[
            "Найдите участок графика, которому принадлежит заданная абсцисса.",
            "На прямом отрезке равным изменениям x соответствуют равные изменения y.",
            f"Число {argument} находится посередине между {left} и {left + width}; "
            "найдите середину между соответствующими ординатами.",
        ],
        solution=[
            f"Абсцисса {argument} лежит на отрезке AB.",
            f"Она делит интервал [{left}; {left + width}] пополам. "
            "Ордината на отрезке также является средним ординат его концов.",
            f"f({argument}) = ({bottom} + {top})/2 = {decimal_text(answer)}.",
        ],
    )


def _derivative_positive_length(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    left = seed % 20
    width = 2 + (seed // 20) % 5
    height = 1 + (seed // 100) % 8
    points = [(left, -height), (left + 2 * width, height),
              (left + 4 * width, -height), (left + 6 * width, height)]
    zeros = [left + width, left + 3 * width, left + 5 * width]
    right = left + 6 * width
    statement = (f"На рисунке график производной f′ — ломаная ABCD: {_vertices(points)}. "
                 f"Найдите суммарную длину промежутков возрастания f на ({left}; {right}). "
                 "Координаты заданы точно.")
    return _task(
        "derivative-positive-length", seed, profile, statement=statement, answer=3 * width,
        figure=_figure(statement, [points], _vertex_labels(points)), difficulty=2,
        hints=[
            "Изображена производная. Возрастание самой f определяется знаком f′.",
            "Выберите участки, где график производной находится выше оси x.",
            "На каждом наклонном отрезке значения на концах противоположны; "
            "нулевая ордината достигается в середине по x.",
        ],
        solution=[
            f"Нули производной: {zeros[0]}, {zeros[1]}, {zeros[2]}.",
            f"f′ > 0 на ({zeros[0]}; {zeros[1]}) и ({zeros[2]}; {right}).",
            f"Их суммарная длина: ({zeros[1]} − {zeros[0]}) + "
            f"({right} − {zeros[2]}) = {3 * width}.",
            "Отдельные граничные точки не влияют на длину интервалов.",
        ],
    )


def _tangent_from_two_points(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    contact = -5 + seed % 11
    ordinate = 1 + (seed // 11) % 8
    slope = Fraction(1 + seed % 17, 2)
    if (seed // 17) % 2:
        slope = -slope
    marked = [(contact - 2, ordinate - 2 * slope), (contact + 2, ordinate + 2 * slope)]
    offsets = [Fraction(index, 8) for index in range(-24, 25)]
    curve = [(contact + dx, ordinate + slope * dx + dx * dx) for dx in offsets]
    tangent = [(contact - 3, ordinate - 3 * slope), (contact + 3, ordinate + 3 * slope)]
    statement = ("На рисунке график f и касательная к нему. Касательная проходит через "
                 f"точки {_vertices(marked)}. Точка касания имеет абсциссу {contact}. "
                 f"Найдите f′({contact}). Координаты заданы точно.")
    labels = [*_vertex_labels(marked), ("T", contact, ordinate)]
    return _task(
        "tangent-from-two-points", seed, profile, statement=statement, answer=slope,
        formula=r"f'(x_0)=\frac{y_B-y_A}{x_B-x_A}",
        figure=_figure(statement, [curve, tangent], labels, dashed=1),
        hints=[
            "Производная в точке касания равна угловому коэффициенту касательной.",
            "Найдите отношение изменения ординаты к изменению абсциссы по двум точкам прямой.",
            f"Вычислите ({decimal_text(marked[1][1])} − ({decimal_text(marked[0][1])}))/"
            f"({marked[1][0]} − ({marked[0][0]})).",
        ],
        solution=[
            "Точки A и B лежат на касательной; для вычисления её наклона этого достаточно.",
            f"Приращение y равно {decimal_text(4 * slope)}, приращение x равно 4.",
            f"Угловой коэффициент равен {decimal_text(4 * slope)}/4 = {decimal_text(slope)}.",
            f"Следовательно, f′({contact}) = {decimal_text(slope)}.",
        ],
    )


def _derivative_turning_point(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    answer = 1 + seed % 100
    slope = 1 + (seed // 100) % 8
    left, right = answer - 2, answer + 3
    points = [(left, -2 * slope), (right, 3 * slope)]
    statement = (f"На интервале ({left}; {right}) график производной f′ — отрезок AB: "
                 f"{_vertices(points)}. Найдите абсциссу точки минимума f. "
                 "Координаты заданы точно.")
    return _task(
        "derivative-turning-point", seed, profile, statement=statement, answer=answer,
        figure=_figure(statement, [points], _vertex_labels(points)),
        hints=[
            "В точке минимума функция перестаёт убывать и начинает возрастать.",
            "Ищите нуль производной, в котором знак меняется с минуса на плюс.",
            f"Наклон отрезка равен ({3 * slope} + {2 * slope})/({right} − ({left})). "
            f"Определите, на сколько нужно увеличить x от {left}, чтобы подняться до y = 0.",
        ],
        solution=[
            f"На отрезке производная растёт с наклоном {slope}.",
            f"От значения −{2 * slope} до нуля она поднимается при увеличении x на 2; "
            f"нуль имеет абсциссу {left} + 2 = {answer}.",
            f"Слева от {answer} производная отрицательна, справа положительна: "
            "f сначала убывает, затем возрастает.",
            f"Поэтому абсцисса точки минимума f равна {answer}.",
        ],
    )


def _antiderivative_initial_value(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    quadratic = 1 + seed % 20
    linear = 1 + (seed // 20) % 7
    initial = 1 + (seed // 140) % 10
    target = 2 + (seed // 1400) % 8
    answer = quadratic * target * target + linear * target + initial
    return _task(
        "antiderivative-initial-value", seed, profile,
        statement=(f"F — первообразная функции f(x) = {2 * quadratic}x + {linear}. "
                   f"Известно F(0) = {initial}. Найдите F({target})."),
        formula=r"F'(x)=f(x)", answer=answer,
        hints=[
            "Нужно восстановить функцию по её производной, сохранив произвольную константу.",
            "Первообразная ax + b имеет вид ax²/2 + bx + C.",
            f"Подставьте x = 0 и F(0) = {initial}, чтобы найти C; затем используйте x = {target}.",
        ],
        solution=[
            f"F(x) = {quadratic}x² + {linear}x + C: её производная равна заданной f.",
            f"При x = 0 получаем C = F(0) = {initial}.",
            f"F({target}) = {quadratic} · {target}² + {linear} · {target} + {initial} = {answer}.",
        ],
    )


def _integral_signed_areas(seed: int, profile: ProfileSource) -> dict:
    seed = _seed(seed)
    upper = 2 + seed % 17
    lower = 1 + (seed // 17) % 7
    width = 2 + (seed // 119) % 5
    points = [(0, -lower), (width, 0), (2 * width, upper), (3 * width, 0)]
    negative = Fraction(width * lower, 2)
    positive = width * upper
    answer = positive - negative
    statement = (f"График f — ломаная ABCD с вершинами {_vertices(points)}. "
                 f"Найдите определённый интеграл ∫ от 0 до {3 * width} f(x) dx. "
                 "Координаты заданы точно.")
    return _task(
        "integral-signed-areas", seed, profile, statement=statement, answer=answer,
        formula=rf"\int_0^{{{3 * width}}} f(x)\,dx",
        figure=_figure(statement, [points], _vertex_labels(points)), difficulty=2,
        hints=[
            "Определённый интеграл учитывает знак функции относительно оси x.",
            "Площадь фигуры над осью берётся со знаком плюс, под осью — со знаком минус.",
            f"Вычтите площадь треугольника с основанием {width} и высотой {lower} "
            f"из площади треугольника с основанием {2 * width} и высотой {upper}.",
        ],
        solution=[
            f"Под осью на [0; {width}] лежит треугольник площади "
            f"{width} · {lower}/2 = {decimal_text(negative)}.",
            f"Над осью на [{width}; {3 * width}] лежит треугольник площади "
            f"{2 * width} · {upper}/2 = {positive}.",
            f"Интеграл равен {positive} − {decimal_text(negative)} = {decimal_text(answer)}.",
        ],
    )


FAMILIES: tuple[Family, ...] = (
    Family(
        "distribution-missing-probability", 6, "Нормировка таблицы распределения",
        ("distribution-table",), _missing_probability,
    ),
    Family(
        "distribution-weighted-mean", 6, "Среднее по таблице распределения",
        ("distribution-table", "distribution-expectation"), _weighted_mean, True,
    ),
    Family(
        "distribution-weighted-variance", 6, "Дисперсия по двум моментам",
        ("distribution-table", "distribution-expectation", "distribution-variance"),
        _weighted_variance, True,
    ),
    Family(
        "distribution-two-point-deviation", 6, "Стандартное отклонение двух исходов",
        ("distribution-table", "distribution-expectation", "distribution-variance",
         "distribution-standard-deviation"), _two_point_deviation,
    ),
    Family(
        "distribution-step-cdf", 6, "Функция распределения в точке скачка",
        ("distribution-table", "distribution-cdf"), _step_cdf,
    ),
    Family(
        "distribution-linear-density", 6, "Нормировка непрерывной плотности",
        ("distribution-density",), _linear_density,
    ),
    Family(
        "distribution-uniform-interval", 6, "Вероятность для равномерного распределения",
        ("distribution-uniform",), _uniform_interval,
    ),
    Family(
        "distribution-exponential-survival", 6, "Хвост показательного распределения",
        ("distribution-exponential", "distribution-cdf"), _exponential_survival,
    ),
    Family(
        "distribution-normal-symmetry", 6, "Симметрия нормального распределения",
        ("distribution-normal",), _normal_symmetry,
    ),
    Family(
        "rational-excluded-root", 7, "Нуль дроби и запрещённый корень",
        ("equation-rational", "equation-domain", "equation-root-selection"),
        _rational_excluded_root, True,
    ),
    Family(
        "radical-extraneous-root", 7, "Корень после возведения в квадрат",
        ("equation-irrational", "equation-domain", "equation-root-selection"),
        _radical_extraneous_root, True,
    ),
    Family(
        "exponential-common-base", 7, "Равенство степеней с общим основанием",
        ("equation-exponential",), _exponential_common_base,
    ),
    Family(
        "logarithmic-product-domain", 7, "Сумма логарифмов и отбор корня",
        ("equation-logarithmic", "equation-domain", "equation-root-selection"),
        _logarithmic_product_domain,
    ),
    Family(
        "absolute-value-selected-root", 7, "Два корня уравнения с модулем",
        ("equation-other-short-answer", "equation-root-selection"),
        _absolute_value_selected_root,
    ),
    Family(
        "power-product-quotient", 8, "Степени с отрицательным показателем",
        ("algebra-powers", "algebra-exact-computation"), _power_product_quotient, True,
    ),
    Family(
        "radical-conjugates", 8, "Сопряжённые выражения с корнем",
        ("algebra-roots", "algebra-exact-computation"), _radical_conjugates,
    ),
    Family(
        "rational-removable-factor", 8, "Сокращение разности квадратов",
        ("algebra-rational-expressions", "algebra-exact-computation"),
        _rational_removable_factor, True,
    ),
    Family(
        "logarithm-difference", 8, "Разность логарифмов как логарифм частного",
        ("algebra-logarithms", "algebra-exact-computation"), _logarithm_difference,
    ),
    Family(
        "trigonometric-double-angle", 8, "Двойной угол и знак косинуса",
        ("algebra-trigonometry", "algebra-exact-computation"), _trigonometric_double_angle,
    ),
    Family(
        "piecewise-function-value", 9, "Значение функции на отрезке графика",
        ("calculus-function-graph",), _piecewise_function_value,
    ),
    Family(
        "derivative-positive-length", 9, "Возрастание по графику производной",
        ("calculus-derivative-graph", "calculus-monotonicity"), _derivative_positive_length,
    ),
    Family(
        "tangent-from-two-points", 9, "Производная по двум точкам касательной",
        ("calculus-tangent",), _tangent_from_two_points, True,
    ),
    Family(
        "derivative-turning-point", 9, "Минимум по смене знака производной",
        ("calculus-derivative-graph", "calculus-monotonicity", "calculus-extrema"),
        _derivative_turning_point, True,
    ),
    Family(
        "antiderivative-initial-value", 9, "Первообразная с начальным условием",
        ("calculus-antiderivative",), _antiderivative_initial_value,
    ),
    Family(
        "integral-signed-areas", 9, "Интеграл как разность площадей",
        ("calculus-function-graph", "calculus-integral"), _integral_signed_areas,
    ),
)

_CATALOG = {family.id: family for family in FAMILIES}


def _section(heading: str, body: str, formula: str | None = None) -> dict:
    return {"heading": heading, "body": " ".join(body.split()), "formula": formula}


def _lesson(sections: list, statement: str, steps: list[str], answer: Fraction | int,
            takeaway: str) -> dict:
    return {
        "sections": sections,
        "example": {"statement": statement, "steps": steps, "answer": decimal_text(answer)},
        "takeaway": takeaway,
    }


_LESSONS = {
    "distribution-missing-probability": _lesson(
        [
            _section("Таблица как полное описание опыта", """
                Таблица распределения связывает каждое возможное значение случайной величины
                с вероятностью этого значения. Здесь важно различать результат измерения
                и его вероятность. Число баллов может быть больше единицы, а вероятность
                не может. В одном испытании величина принимает ровно одно из перечисленных
                различных значений. Поэтому события, соответствующие строкам полной таблицы,
                несовместны и вместе описывают все исходы опыта. Прежде чем восстанавливать
                пропуск, найдите в условии подтверждение полноты списка. Если показаны лишь
                некоторые результаты, сумма видимых вероятностей может быть меньше единицы
                и оставшаяся масса не обязательно относится к одной пропущенной строке.
            """),
            _section("Откуда берётся условие нормировки", """
                Вероятность достоверного события равна единице. Достоверным здесь является
                событие «случайная величина приняла какое-нибудь своё возможное значение».
                Оно составлено из несовместных событий отдельных строк. По правилу сложения
                их вероятности складываются без поправки на пересечение. Так получается
                условие нормировки таблицы. Если неизвестна ровно одна вероятность, перенесите
                сумму остальных в другую часть равенства. Величины из столбца значений
                в это уравнение не входят. Не нужно ни умножать их на вероятности, ни искать
                среднее: сейчас восстанавливается полная вероятность, а не характеристика
                размера случайного результата.
            """, r"p_1+\dots+p_n=1,\qquad p_k=1-\sum_{i\ne k}p_i"),
            _section("Как работать с записью данных", """
                Перепишите известные вероятности в одной форме: обыкновенными дробями,
                конечными десятичными дробями или долями единицы после перевода процентов.
                Смешивать запись в процентах и долях без перевода нельзя: сорок процентов
                означают четыре десятых, а не сорок. Если вероятность представлена отношением
                числа исходов к их общему количеству, сначала убедитесь в равновозможности
                этих исходов. В готовой таблице сами значения могут идти в любом порядке;
                перестановка целых строк ничего не меняет. Однако отделение вероятности
                от своего значения меняет распределение, поэтому при переписывании сохраняйте
                пары и отмечайте именно ту ячейку, которую нужно восстановить.
            """),
            _section("Проверка и границы метода", """
                Полученная вероятность должна лежать между нулём и единицей включительно.
                Отрицательный результат означает, что известные вероятности уже превышают
                единицу: такие данные не задают распределение. После вычисления подставьте
                результат обратно в таблицу и ещё раз сложите все вероятности. Нулевая
                вероятность математически допустима, хотя в обычном перечне возможных
                исходов чаще оставляют только строки с положительной вероятностью. Если
                неизвестны две независимые вероятности, одной нормировки обычно недостаточно:
                требуется дополнительное условие об их отношении или другом событии.
                Не пытайтесь автоматически делить остаток поровну, если равенство вероятностей
                не следует из описания опыта.
            """),
        ],
        "X принимает только значения 1, 4 и 9 с вероятностями 0,15, p и 0,35. Найдите p.",
        [
            "Все возможные значения перечислены, поэтому 0,15 + p + 0,35 = 1.",
            "Сумма известных вероятностей равна 0,5; следовательно, p = 1 − 0,5 = 0,5.",
            "Проверяем восстановленную таблицу: все вероятности положительны и "
            "0,15 + 0,5 + 0,35 = 1. Значения один, четыре и девять в сумму вероятностей не входят.",
        ], Fraction(1, 2),
        "В полной таблице сумма вероятностей равна единице; вычтите известную часть.",
    ),
    "distribution-weighted-mean": _lesson(
        [
            _section("Что означает среднее случайной величины", """
                Математическое ожидание описывает среднее значение в длинной серии повторений
                одного случайного опыта. Оно не предсказывает результат ближайшего испытания
                и не обязано совпадать с одним из возможных исходов. Например, среднее число
                полученных баллов может быть дробным, хотя каждый отдельный приз приносит
                целое число баллов. Для расчёта нужна вся таблица распределения: возможные
                значения и вероятности, с которыми они появляются. Большой, но очень редкий
                приз не должен влиять на среднее так же сильно, как частый приз. Именно эту
                разницу учитывают вероятностные веса, стоящие рядом со значениями.
            """),
            _section("Почему значения умножают на вероятности", """
                Представьте сто испытаний с частотами, точно соответствующими вероятностям.
                Если вероятность некоторого значения равна одной четверти, это значение
                встретится двадцать пять раз. В суммарный результат оно внесёт своё значение,
                умноженное на двадцать пять. Чтобы перейти от суммы за сто испытаний к
                среднему за одно испытание, нужно разделить на сто. Вклад получится равным
                значению, умноженному на одну четверть. Складывая такие вклады по всем
                строкам, получаем формулу ожидания. Это объясняет, почему нельзя просто
                сложить возможные значения и разделить на число строк, когда вероятности
                этих строк различны.
            """, r"M(X)=x_1p_1+x_2p_2+\dots+x_np_n"),
            _section("Условия применения и порядок действий", """
                Сначала убедитесь, что таблица перечисляет все возможные значения и что
                вероятности неотрицательны, а их сумма равна единице. Затем для каждой строки
                найдите одно произведение значения на его вероятность. Сложите произведения,
                сохраняя точные дроби до конца вычисления. Нулевая строка не вносит вклада
                в сумму, но её вероятность нужна при проверке нормировки. Не меняйте местами
                вероятности соседних строк: это уже другое распределение и обычно другое
                ожидание. Если вероятности записаны процентами, предварительно переведите
                их в доли единицы. Единицы ожидания совпадают с единицами самой величины.
            """),
            _section("Как проверить смысл результата", """
                Среднее с положительными весами находится между наименьшим и наибольшим
                возможными значениями. Выход за эти границы означает арифметическую ошибку
                или неверно прочитанную таблицу. Если все значения увеличить на одинаковое
                число, ожидание увеличится на это же число: дополнительный вклад умножается
                на сумму вероятностей, то есть на единицу. Это удобная проверка для таблиц
                с большими числами: можно временно отсчитать значения от общего начала.
                При равных вероятностях правило действительно превращается в обычное
                среднее арифметическое. В остальных случаях деление на количество разных
                исходов не заменяет взвешивание и не учитывает устройство опыта.
            """),
        ],
        "X принимает значения 0, 3 и 8 с вероятностями 0,25, 0,5 и 0,25. Найдите M(X).",
        [
            "Проверяем таблицу: 0,25 + 0,5 + 0,25 = 1. Все вероятности положительны.",
            "Учитываем веса: M(X) = 0 · 0,25 + 3 · 0,5 + 8 · 0,25 = 0 + 1,5 + 2 = 3,5.",
            "Среднее находится между нулём и восемью. Оно не обязано быть возможным "
            "исходом; дробное значение здесь имеет смысл результата за одно испытание в среднем.",
        ],
        Fraction(7, 2),
        "Проверьте нормировку, умножьте каждое значение на его вероятность и сложите вклады.",
    ),
    "distribution-weighted-variance": _lesson(
        [
            _section("Зачем измерять разброс", """
                Две случайные величины могут иметь одинаковое математическое ожидание,
                но давать совершенно разные результаты в отдельных испытаниях. Одна почти
                всегда близка к среднему, другая часто отклоняется далеко от него. Дисперсия
                различает такие ситуации: это средний квадрат отклонения от ожидания.
                Обычное среднее отклонение со знаком не годится, потому что положительные
                и отрицательные отклонения взаимно компенсируются. Возведение в квадрат
                делает каждый вклад неотрицательным и сильнее учитывает большие отклонения.
                В таблице распределения размер вклада по-прежнему зависит от вероятности
                строки, поэтому редкий результат получает небольшой вес, а частый — большой.
            """, r"D(X)=\sum_i (x_i-M(X))^2p_i"),
            _section("Почему работает формула двух моментов", """
                Раскройте квадрат разности в определении дисперсии. Первые слагаемые дают
                среднее квадратов значений. Вторые содержат среднее самой величины,
                умноженное на её же ожидание. Последние являются квадратом ожидания,
                умноженным на сумму вероятностей. После использования нормировки два
                последних вклада объединяются в минус квадрат ожидания. Получается удобное
                правило: из среднего квадратов вычитают квадрат среднего. Эти выражения
                похожи по названию, но выполняются в разном порядке. Для среднего квадратов
                сначала возводят каждое значение в квадрат; для квадрата среднего сначала
                вычисляют одно общее среднее и лишь затем возводят его в квадрат.
            """, r"D(X)=M(X^2)-(M(X))^2"),
            _section("Три строки вычислений", """
                Первая строка решения проверяет нормировку и находит математическое
                ожидание по исходной таблице. Вторая находит математическое ожидание
                квадрата величины: значения возводятся в квадрат, но вероятности остаются
                прежними. Третья выполняет вычитание по формуле дисперсии. Сохраняйте точные
                промежуточные значения. Округление среднего особенно нежелательно, потому
                что потом оно возводится в квадрат и ошибка увеличивается. Если данных
                немного, результат можно проверить непосредственно через квадраты отклонений.
                Эта дополнительная проверка использует те же вероятности и помогает заметить
                ошибку знака, пропущенную строку или случайное возведение вероятности в квадрат.
            """),
            _section("Смысл и типичные ловушки", """
                Дисперсия никогда не бывает отрицательной: её определение состоит из суммы
                неотрицательных вкладов. Нулевое значение означает отсутствие разброса при
                условии, что учитываются только исходы положительной вероятности. Если
                величина измеряется в баллах, дисперсия измеряется в квадратных баллах.
                Добавление одинаковой постоянной ко всем значениям меняет ожидание, но
                сохраняет расстояния до него, поэтому дисперсия не меняется. При умножении
                всех значений на число дисперсия умножается на квадрат этого числа.
                Не путайте распределение с выборкой наблюдений: здесь вероятности известны,
                и поправка с делением на число наблюдений минус один не применяется.
            """),
        ],
        "X принимает значения 1, 3 и 5 с вероятностями 0,25, 0,5 и 0,25. Найдите D(X).",
        [
            "Вероятности дают единицу. Ожидание равно 1 · 0,25 + 3 · 0,5 + 5 · 0,25 = 3.",
            "Среднее квадратов: M(X²) = 1 · 0,25 + 9 · 0,5 + 25 · 0,25 = 11.",
            "Дисперсия равна 11 − 3² = 2. Проверка отклонениями: "
            "(−2)² · 0,25 + 0² · 0,5 + 2² · 0,25 = 2; оба способа согласуются.",
        ], 2,
        "Среднее квадратов минус квадрат среднего; вероятности не возводятся в квадрат.",
    ),
    "distribution-two-point-deviation": _lesson(
        [
            _section("Возвращение к исходным единицам", """
                Стандартное отклонение, также называемое средним квадратическим отклонением,
                характеризует масштаб разброса случайной величины. Оно равно арифметическому
                квадратному корню из дисперсии. Если исходная величина измерена в метрах,
                её дисперсия выражается в квадратных метрах, а стандартное отклонение снова
                в метрах. Поэтому его удобно сравнивать с самими значениями и средним.
                Это характеристика распределения, а не вероятность события и не обещание,
                что всякое наблюдение отклонится от среднего именно на такую величину.
                В общем распределении отклонения разных исходов могут существенно различаться;
                стандартное отклонение объединяет их с учётом вероятностных весов.
            """, r"\sigma(X)=\sqrt{D(X)}"),
            _section("Два равновероятных значения", """
                Когда случайная величина принимает два различных значения с равными
                вероятностями, её ожидание лежит ровно посередине между ними. Расстояния
                от обоих значений до этой середины одинаковы. Следовательно, оба квадрата
                отклонений тоже одинаковы, а их среднее совпадает с любым из них.
                Извлечение квадратного корня возвращает общее расстояние от исхода до
                середины. Поэтому стандартное отклонение такой величины равно половине
                расстояния между двумя значениями. Это короткое правило следует из
                определения, но требует именно равенства вероятностей. При других весах
                середина уже не является ожиданием, а расстояния до него перестают совпадать.
            """, r"P(X=a)=P(X=b)=\frac12\quad\Longrightarrow\quad\sigma=\frac{|b-a|}{2}"),
            _section("Полное решение через определения", """
                Даже если симметрия заметна сразу, полезно уметь записать полное решение.
                Сначала убедитесь, что вероятности двух строк в сумме равны единице.
                Найдите среднее арифметическое значений, поскольку веса одинаковы.
                Затем вычислите квадрат отклонения каждого исхода от найденного среднего
                и умножьте его на соответствующую вероятность. Сумма этих произведений
                является дисперсией. Последний отдельный шаг — извлечение неотрицательного
                квадратного корня. Не останавливайтесь на дисперсии, если в вопросе требуется
                стандартное отклонение. В решении удобно подписывать каждую характеристику
                своим обозначением, чтобы не перепутать ответ с промежуточным результатом.
            """),
            _section("Как контролировать знак и масштаб", """
                Уравнение, связывающее квадрат стандартного отклонения с дисперсией, формально
                имеет два корня, когда дисперсия положительна. Но стандартное отклонение
                по определению неотрицательно, поэтому отрицательный корень исключается.
                Если сдвинуть оба значения на одинаковую величину, расстояние между ними
                останется прежним, и стандартное отклонение сохранится. Если увеличить
                оба значения в несколько раз, стандартное отклонение увеличится в модуль
                этого множителя. Эти свойства позволяют быстро заметить несогласованный
                результат. Для двух равновероятных исходов дополнительно проверьте: двойное
                стандартное отклонение должно совпасть с расстоянием между крайними значениями,
                независимо от того, положительны они или отрицательны.
            """),
        ],
        "X принимает значения 4 и 12, каждое с вероятностью 0,5. Найдите σ(X).",
        [
            "Среднее равно (4 + 12)/2 = 8. Отклонения двух исходов от среднего равны −4 и 4.",
            "Дисперсия: D(X) = 16 · 0,5 + 16 · 0,5 = 16.",
            "Стандартное отклонение σ(X) = √16 = 4. Берём положительный корень; "
            "он равен половине расстояния между четырьмя и двенадцатью, как и должно быть.",
        ], 4,
        "Стандартное отклонение — неотрицательный корень из дисперсии, в исходных единицах.",
    ),
    "distribution-step-cdf": _lesson(
        [
            _section("Вероятность накапливается слева направо", """
                Функция распределения связывает порог со всей вероятностью, накопленной
                к этому порогу. В этом уроке используется определение через нестрогое
                неравенство: учитываются значения, меньшие порога или равные ему. Всегда
                читайте определение в конкретном условии: в учебных источниках встречается
                также соглашение со строгим неравенством. Для непрерывного распределения
                различие в отдельной точке не влияет на вероятность, а для дискретной
                величины влияет. Если порог совпадает со значением из таблицы, вероятность
                соответствующей строки включается в нашу сумму. Именно чтение границы
                события является главным шагом перед любыми арифметическими вычислениями.
            """, r"F(t)=P(X\leq t)"),
            _section("Почему получается лестница", """
                Упорядочите различные значения случайной величины по возрастанию. Пока порог
                меньше самого маленького значения, ни одна строка не подходит, поэтому
                накопленная вероятность равна нулю. Когда порог достигает первого значения,
                к сумме добавляется вероятность первой строки. Между первым и вторым
                значениями новых исходов нет, так что функция остаётся постоянной.
                При следующем значении возникает очередной скачок. После последнего
                значения учтены все строки и функция равна единице. Высота каждого скачка
                равна вероятности соответствующего исхода, а не самому значению величины.
                Так таблица распределения превращается в ступенчатую функцию.
            """),
            _section("Свойства для быстрой проверки", """
                Функция распределения не убывает: увеличение порога может только добавить
                новые допустимые исходы, но не исключить уже учтённые. Её значения лежат
                от нуля до единицы. При выбранном определении значение в точке скачка
                совпадает со значением сразу справа от неё. Если вы получили меньший
                результат для большего порога, проверьте направление неравенства и порядок
                строк. Чтобы найти вероятность промежутка, иногда удобно вычесть две
                накопленные вероятности. Однако отдельно проверьте его концы: разность
                значений функции в правой и левой границах исключает саму левую границу,
                но включает правую.
            """, r"P(a<X\leq b)=F(b)-F(a)"),
            _section("Практический алгоритм чтения таблицы", """
                Обведите вопрос: нужна вероятность отдельного значения или значение функции
                распределения? Для второго варианта проведите мысленную границу по указанному
                порогу и выберите все подходящие строки. Не нужно умножать значения
                случайной величины на вероятности, как при расчёте ожидания. Здесь значения
                служат только для выбора строк, а складываются исключительно вероятности.
                Если порог совпал с табличным значением, проговорите вслух, включается ли
                равенство согласно определению. После суммирования сравните ответ с соседними
                накопленными вероятностями. Дополнительная проверка — вычесть из единицы
                вероятности всех значений, строго превышающих порог: результат должен совпасть.
            """),
        ],
        "X принимает значения 1, 4 и 9 с вероятностями 0,2, 0,5 и 0,3. "
        "При F(t) = P(X ≤ t) найдите F(4).",
        [
            "Событие X ≤ 4 включает два исхода: один и четыре. Девять превышает порог.",
            "Складываем вероятности выбранных строк: F(4) = 0,2 + 0,5 = 0,7.",
            "Проверяем дополнением: 1 − P(X = 9) = 1 − 0,3 = 0,7. "
            "Если бы равенство четырём исключалось, "
            "получилось бы другое событие и другая вероятность.",
        ], Fraction(7, 10),
        "Для F(t) = P(X ≤ t) сложите вероятности всех значений до порога включительно.",
    ),
    "distribution-linear-density": _lesson(
        [
            _section("Плотность и вероятность различаются", """
                Плотность описывает распределение непрерывной случайной величины через площадь.
                Вероятность попадания в интервал равна площади под графиком плотности
                над этим интервалом. Отдельная высота графика не является вероятностью
                данного значения: у непрерывной величины вероятность каждой отдельной точки
                равна нулю. Высота плотности может даже превышать единицу, если участок
                достаточно узкий; это не нарушает ограничений на вероятность. Проверять
                нужно не отдельные высоты относительно единицы, а неотрицательность всей
                плотности и суммарную площадь. В этом семействе график плотности на носителе
                является отрезком прямой, поэтому нужную площадь можно найти геометрически.
            """),
            _section("Два обязательных условия", """
                Любая плотность неотрицательна на всей числовой прямой и имеет общую площадь,
                равную единице. Первое условие исключает отрицательные вероятности интервалов.
                Второе выражает достоверность попадания величины куда-нибудь на числовую
                прямую. Если по условию плотность равна нулю вне заданного отрезка,
                вся её площадь сосредоточена внутри этого отрезка. Не нужно продолжать
                наклонную прямую за указанные границы: там действует другая часть определения.
                Это особенно важно справа от носителя, где продолжение возрастающей
                прямой дало бы бесконечную площадь и перестало бы описывать распределение.
                Границы носителя являются существенной частью модели.
            """, r"f(x)\geq0,\qquad\int_{-\infty}^{+\infty}f(x)\,dx=1"),
            _section("Линейная плотность через треугольник", """
                Пусть на отрезке от нуля до положительного числа плотность равна этому
                аргументу, умноженному на неизвестный коэффициент. В левом конце высота
                нулевая, в правом равна произведению коэффициента на длину отрезка.
                Вместе с осью абсцисс график ограничивает прямоугольный треугольник.
                Его площадь равна половине произведения основания на высоту. Приравняйте
                эту площадь к единице и выразите коэффициент. Длина отрезка участвует
                в произведении дважды: один раз как основание, другой раз как часть
                высоты. Поэтому в знаменателе ответа возникает квадрат правой границы,
                а не сама граница.
            """, r"\frac12\,b\,(cb)=1\quad\Longrightarrow\quad c=\frac{2}{b^2},\quad b>0"),
            _section("Проверка найденной модели", """
                После вычисления коэффициента вернитесь к обоим условиям плотности.
                Положительный коэффициент на неотрицательном отрезке обеспечивает
                неотрицательную высоту. Подстановка в формулу площади должна дать ровно
                единицу. Можно дополнительно посмотреть, как модель меняется при удвоении
                правой границы: коэффициент уменьшается в четыре раза, иначе площадь
                выросла бы. Для вероятности более короткого интервала используйте только
                площадь над этим интервалом, а не всю нормировочную площадь заново.
                На участке от нуля до внутренней точки снова получится треугольник.
                Между двумя положительными точками удобнее взять разность двух таких
                площадей или вычислить площадь трапеции.
            """),
        ],
        "Плотность равна c·x на [0; 5] и нулю вне этого отрезка. Найдите c.",
        [
            "Основание треугольника равно пяти, его высота в правом конце равна 5c.",
            "Из нормировки получаем 5 · 5c / 2 = 1, то есть 25c = 2 и c = 0,08.",
            "Проверка: высота равна 0,4, площадь равна 5 · 0,4 / 2 = 1. "
            "Плотность на всём носителе неотрицательна, вне носителя она нулевая.",
        ], Fraction(2, 25),
        "Нормируется площадь под плотностью, а не её высота; учитывайте границы носителя.",
    ),
    "distribution-uniform-interval": _lesson(
        [
            _section("Что значит равномерное распределение", """
                При равномерном распределении на отрезке равные по длине участки внутри
                этого отрезка имеют одинаковые вероятности. Это утверждение касается
                интервалов, а не отдельных точек: каждая отдельная точка по-прежнему
                имеет нулевую вероятность. Плотность постоянна на всём отрезке и нулевая
                вне него. В задачах такую модель используют для случайного момента
                внутри заданного промежутка времени или случайной координаты на отрезке.
                Равномерность должна быть прямо задана или обоснована устройством выбора.
                Само наличие нижней и верхней границ ещё не означает, что все участки
                между ними выбираются с одинаковой частотой.
            """),
            _section("Почему вероятность равна отношению длин", """
                Полная площадь под постоянной плотностью является прямоугольником и равна
                единице. Следовательно, высота прямоугольника равна обратной длине всего
                отрезка. Над нужным внутренним участком высота остаётся той же, меняется
                только основание. Его площадь, то есть вероятность, равна длине участка,
                делённой на длину полного отрезка. Начало координат при этом не важно:
                сдвиг обеих границ на одно число не меняет длину. Именно поэтому
                в числителе и знаменателе стоят разности границ. Использование самих
                правых концов вместо разностей ошибочно, когда левый конец не является нулём.
            """, r"P(c\leq X\leq d)=\frac{d-c}{b-a},\quad a\leq c\leq d\leq b"),
            _section("Сначала пересечение, затем вычисление", """
                Формула отношения длин в простом виде предполагает, что нужный интервал
                целиком находится внутри носителя распределения. Если одна граница вышла
                за носитель, сначала найдите пересечение двух интервалов. Вероятность
                участка вне носителя равна нулю, поэтому добавлять его длину нельзя.
                Если пересечение пусто, ответ нулевой; если событие покрывает весь носитель,
                ответ равен единице. Концы можно включать или исключать без изменения
                вероятности, потому что отдельные точки имеют нулевую массу. При вычислении
                следите за единицами: обе длины должны быть измерены одинаково, иначе
                их отношение не станет корректной безразмерной вероятностью.
            """),
            _section("Связь с функцией распределения", """
                До левого конца накопленная вероятность равна нулю, после правого — единице.
                Внутри отрезка она растёт линейно: путь от левого конца до текущего
                порога делится на полную длину. Поэтому вероятность внутреннего интервала
                можно получить и вычитанием двух значений функции распределения. Этот
                способ полезен, когда условие задано через накопленные вероятности.
                Середина носителя делит вероятность пополам и совпадает с ожиданием,
                поскольку распределение симметрично. Но симметрия сама по себе не означает
                равномерность: например, у нормального распределения центральные участки
                плотнее крайних. Применять отношение длин можно только после проверки
                именно равномерного характера модели.
            """, r"F(t)=\frac{t-a}{b-a}\quad(a\leq t\leq b)"),
        ],
        "X равномерно распределена на [10; 50]. Найдите P(18 ≤ X ≤ 34).",
        [
            "Нужный участок целиком лежит внутри носителя. Полная длина равна 50 − 10 = 40.",
            "Длина благоприятного участка равна 34 − 18 = 16. Вероятность равна 16/40 = 0,4.",
            "Для проверки можно разделить носитель на пять равных отрезков длины восемь. "
            "Нужный участок занимает два таких отрезка, "
            "поэтому имеет две пятых полной вероятности.",
        ], Fraction(2, 5),
        "При равномерном распределении найдите пересечение с носителем и разделите длины.",
    ),
    "distribution-exponential-survival": _lesson(
        [
            _section("Модель времени ожидания", """
                Показательное распределение описывает неотрицательное время ожидания
                в модели с постоянной интенсивностью событий. Его параметр интенсивности
                положителен и имеет единицы, обратные единицам времени. Если время
                измеряется в минутах, интенсивность измеряется в обратных минутах.
                Чем больше интенсивность, тем короче характерное ожидание. Математическое
                ожидание равно обратной интенсивности, но в задаче о вероятности нельзя
                подменять случайное время его средним. Вероятность ожидать дольше среднего
                не равна нулю: распределение допускает сколь угодно большие положительные
                времена. При этом вероятность отрицательного ожидания равна нулю,
                а вероятность любого отдельного момента тоже нулевая.
            """),
            _section("Функция распределения и хвост", """
                Для неотрицательного порога функция распределения показывает вероятность
                дождаться события не позднее этого порога. Хвостовая вероятность отвечает
                противоположному вопросу: событие к данному моменту ещё не наступило.
                Эти два события вместе достоверны, поэтому их вероятности в сумме
                дают единицу. У показательного распределения хвост задаётся особенно
                просто — экспонентой с отрицательным произведением интенсивности на время.
                На нулевом пороге он равен единице, а с увеличением положительного
                времени убывает к нулю. Если при вычислении ожидания «дольше» получилась
                вероятность, растущая с порогом, вероятно, перепутаны функция распределения
                и её дополнение.
            """, r"F(t)=1-e^{-\lambda t},\quad P(T>t)=e^{-\lambda t},\quad t\geq0"),
            _section("Точный ответ без приближённых логарифмов", """
                В некоторых условиях порог выражен через натуральный логарифм. Не спешите
                заменять его десятичным приближением. Сначала подставьте символическую
                запись в показатель экспоненты и сократите совпадающие множители.
                Натуральный логарифм является обратной операцией к возведению числа
                в степень с основанием натуральной экспоненты. Поэтому экспонента
                от логарифма положительного числа возвращает само число, а минус
                перед логарифмом даёт обратное число. Условие положительности аргумента
                обязательно; для положительного порога в используемых задачах аргумент
                дополнительно больше единицы. Такой порядок действий даёт точную дробь
                и избавляет от ненужного округления промежуточного времени.
            """, r"e^{-\ln q}=\frac1q,\quad q>1"),
            _section("Проверка модели и свойство отсутствия памяти", """
                Перед расчётом согласуйте единицы порога и интенсивности: их произведение
                должно быть безразмерным. Проверьте положительность интенсивности и
                неотрицательность времени, затем определите направление события.
                Особое свойство этой модели состоит в отсутствии памяти: если событие
                ещё не наступило, вероятность ждать дополнительно заданное время
                такая же, как в начале наблюдения. Это следует из отношения двух
                экспоненциальных хвостов. Свойство нельзя автоматически переносить на
                произвольное распределение срока службы или времени ожидания.
                Для ответа в кратком формате сохраняйте точную дробь, пока не убедитесь,
                что она имеет конечную десятичную запись либо условие явно требует округления.
            """),
        ],
        "T имеет показательное распределение с λ = 3 мин⁻¹. Найдите P(T > ln(8)/3).",
        [
            "Аргумент логарифма больше единицы, "
            "поэтому порог положителен и формула хвоста применима.",
            "Произведение интенсивности на время равно 3 · ln(8)/3 = ln(8).",
            "Вероятность равна e^(−ln(8)) = 1/8 = 0,125. Натуральный логарифм "
            "не вычислялся приближённо; ответ получен точно и находится между нулём и единицей.",
        ], Fraction(1, 8),
        "Событию «ждать дольше» соответствует e^(−λt); сначала упростите показатель точно.",
    ),
    "distribution-normal-symmetry": _lesson(
        [
            _section("Центр и масштаб нормального распределения", """
                Нормальное распределение задаётся математическим ожиданием и положительным
                стандартным отклонением. Его плотность имеет симметричную колоколообразную
                форму. Ожидание определяет положение центра, а стандартное отклонение —
                масштаб разброса. Сдвиг центра переносит график по горизонтали, не
                разрушая симметрию. Из симметрии следует, что по каждую сторону от
                среднего лежит половина всей вероятности. Однако нельзя делить
                произвольный интервал пополам без проверки его расположения относительно
                центра. Для применения симметрии сравнивают расстояния границ до среднего,
                а не просто их знаки относительно нуля: центр распределения вовсе
                не обязан находиться в начале координат.
            """),
            _section("Симметричный интервал и два хвоста", """
                Рассмотрим интервал с границами на одинаковом расстоянии слева и справа
                от среднего. Дополнение к попаданию внутрь состоит из левого и правого
                хвостов. Отражение относительно центра переводит один хвост в другой,
                поэтому их вероятности равны. Если вероятность центрального интервала
                дана, сначала вычтите её из единицы: получится общая вероятность
                обоих хвостов. Затем разделите остаток пополам, чтобы получить один
                нужный хвост. Делить пополам саму центральную вероятность следует
                в другой задаче — когда нужен участок от среднего до одной границы.
                Выбор числителя определяется самим событием, а не знакомой формулой.
            """, r"P(X\geq\mu+d)=\frac{1-P(\mu-d\lt X\lt\mu+d)}2,\quad d\gt0"),
            _section("Что делать с точными данными", """
                В учебной задаче центральная вероятность может быть задана как точное
                значение модели. Тогда для ответа достаточно правил вероятностей
                и симметрии; вычислять нормальную функцию распределения по таблице
                или подставлять приближённые коэффициенты не нужно. Если указан
                только центр, но не масштаб и не вероятность интервала, численную
                вероятность произвольного хвоста обычно определить невозможно.
                Знакомое приближённое правило о доле наблюдений в пределах стандартного
                отклонения не превращает округлённую величину в точное данное.
                Различайте сведения, действительно приведённые в условии, и приблизительные
                ориентиры из памяти. В данном семействе необходимые вероятности сообщены явно.
            """),
            _section("Непрерывность и окончательная проверка", """
                У нормального распределения вероятность отдельной точки равна нулю.
                Поэтому включение конечной границы в хвост или исключение её из
                центрального интервала не меняет численного ответа. Это свойство
                непрерывной модели, а не универсальное правило для любых таблиц
                распределения. После расчёта сложите центральную вероятность и
                удвоенную вероятность хвоста: должна получиться единица. Один
                внешний хвост при положительной ширине центрального интервала
                меньше половины. При увеличении симметричного центрального интервала
                его вероятность растёт, а каждый хвост уменьшается. Эти соотношения
                позволяют проверить направление вычислений даже без знания стандартного
                отклонения и без графика плотности с числовой шкалой.
            """),
        ],
        "X нормально распределена с μ = 40. Известно точное значение "
        "P(34 < X < 46) = 0,76. Найдите P(X ≥ 46).",
        [
            "Обе границы удалены от среднего сорок на шесть, значит хвосты симметричны.",
            "За пределами центрального интервала остаётся вероятность 1 − 0,76 = 0,24.",
            "Каждый хвост имеет вероятность 0,24/2 = 0,12. Проверка: "
            "0,76 + 2 · 0,12 = 1. Включение точки сорок шесть ничего не меняет, "
            "поскольку её вероятность равна нулю.",
        ], Fraction(3, 25),
        "Проверьте равноудалённость границ: "
        "два симметричных хвоста делят остаток вероятности поровну.",
    ),
    "rational-excluded-root": _lesson(
        [
            _section("Когда дробь действительно равна нулю", """
                Рациональное уравнение может содержать неизвестную в знаменателе. Начинать
                его решение нужно с области допустимых значений: каждый знаменатель
                должен отличаться от нуля. Дробь равна нулю тогда и только тогда,
                когда её числитель равен нулю, а знаменатель определён и ненулевой.
                Эти два требования работают одновременно. Если числитель и знаменатель
                обратились в ноль при одном значении, выражение не стало нулевой
                дробью: оно вообще не определено. Поэтому найденный нуль числителя
                пока является лишь кандидатом в корни. Чтобы назвать его корнем
                исходного уравнения, необходимо отдельно проверить все ограничения знаменателя.
            """, r"\frac{P(x)}{Q(x)}=0\iff P(x)=0\ \text{и}\ Q(x)\ne0"),
            _section("Разложение квадратного числителя", """
                В этом семействе числитель является приведённым квадратным трёхчленом.
                Для разложения удобно подобрать два числа, сумма которых совпадает
                с коэффициентом при неизвестной с противоположным знаком, а произведение
                совпадает со свободным членом. Тогда числитель превращается в произведение
                двух линейных множителей. Нулевым произведение становится при нулевом
                значении хотя бы одного множителя. Если подбор неудобен, используйте
                дискриминант и обычную формулу корней квадратного уравнения. Способ
                нахождения кандидатов не меняет ограничений исходной дроби: область
                допустимых значений была определена до преобразований и должна сопровождать
                решение до окончательного отбора ответа.
            """, r"x^2-(a+b)x+ab=(x-a)(x-b)"),
            _section("Почему сокращение не возвращает запрещённую точку", """
                После разложения может обнаружиться общий множитель в числителе
                и знаменателе. Его можно сократить только там, где он не равен нулю.
                Полученное выражение совпадает с исходным на исходной области определения,
                но может быть определено и в дополнительных точках. Эти дополнительные
                точки не становятся допустимыми для первоначальной задачи. Записывайте
                ограничение рядом с сокращённой формулой, чтобы не потерять его
                при дальнейших вычислениях. Частая ошибка состоит в том, что ученик
                решает только квадратное уравнение числителя и записывает оба корня.
                Другая ошибка — механически объявлять любое совпадение нулей допустимым
                из-за внешне похожих множителей в дроби.
            """),
            _section("Проверка исходным выражением", """
                Проверять нужно именно исходную дробь, а не только полученное после
                сокращения линейное равенство. Для каждого кандидата сначала вычислите
                знаменатель. Если он нулевой, кандидат сразу исключается; делить
                на него нельзя. Для оставшегося кандидата найдите числитель и убедитесь,
                что он равен нулю. Такой порядок проверки короче и надёжнее,
                чем попытка подставить число во всю дробь сразу. Обратите внимание
                на вопрос задачи: если требуется один числовой ответ, отбор должен
                действительно оставить единственный допустимый корень или условие должно
                дополнительно указывать нужный. Нельзя произвольно выбрать понравившийся
                корень из нескольких допустимых результатов.
            """),
        ],
        "Решите уравнение (x² − 11x + 24)/(x − 3) = 0.",
        [
            "Из знаменателя получаем ограничение x ≠ 3. Числитель раскладывается "
            "как (x − 3)(x − 8), поскольку 3 + 8 = 11 и 3 · 8 = 24.",
            "Нули числителя — три и восемь. Первый запрещён областью определения; остаётся восемь.",
            "Проверяем исходную дробь при x = 8: числитель 64 − 88 + 24 = 0, "
            "знаменатель 8 − 3 = 5. Получаем 0/5 = 0, значит ответ равен 8.",
        ], 8,
        "Нули числителя проверяйте по исходному знаменателю; сокращение не отменяет ОДЗ.",
    ),
    "radical-extraneous-root": _lesson(
        [
            _section("Что означает арифметический корень", """
                Квадратный корень в действительных числах определён только для
                неотрицательного подкоренного выражения. Его значение также всегда
                неотрицательно. Поэтому уравнение с корнем в левой части накладывает
                два разных требования: подкоренное выражение должно быть допустимым,
                а правая часть должна иметь неотрицательный знак. Второе требование
                легко забыть, потому что правая часть внешне является обычным
                многочленом и сама по себе определена при любых действительных
                значениях. Но отрицательное число не может равняться арифметическому
                квадратному корню. Запишите оба ограничения до преобразования,
                чтобы затем ясно отличать корни исходного уравнения от кандидатов.
            """, r"\sqrt{A(x)}=B(x)\quad\Longrightarrow\quad A(x)\geq0,\ B(x)\geq0"),
            _section("Что меняется при возведении в квадрат", """
                Равные числа имеют равные квадраты, поэтому любой корень исходного
                уравнения удовлетворяет уравнению после возведения в квадрат.
                Обратное утверждение без ограничений неверно: противоположные числа
                тоже имеют равные квадраты. Таким образом, возведение в квадрат
                может добавить посторонние корни. Если заранее известно, что обе
                части неотрицательны, операция становится равносильной. В решении
                можно пойти любым из двух путей: сохранять ограничения на каждом
                шаге или найти всех кандидатов и проверить их подстановкой.
                В учебной записи полезно делать и то и другое: ограничение
                объясняет причину отбора, а подстановка подтверждает вычисления.
            """, r"\sqrt{A(x)}=B(x)\iff A(x)=B(x)^2,\quad B(x)\geq0"),
            _section("Квадратное уравнение как промежуточный этап", """
                После возведения линейной правой части в квадрат обычно получается
                квадратное уравнение. Аккуратно раскройте квадрат разности: средний
                член содержит удвоенное произведение, а не просто одно произведение.
                Перенесите все слагаемые в одну часть и приведите подобные члены.
                Затем разложите трёхчлен на множители или используйте дискриминант.
                На этом этапе не объявляйте каждый полученный корень окончательным.
                Подпишите их как кандидатов и сравните с ранее найденной областью
                допустимых значений и ограничением знака правой части. Само
                квадратное уравнение уже не хранит информацию о том, какой
                знак имели части исходного равенства до возведения в квадрат.
            """),
            _section("Как проверять и оформлять отбор", """
                Для каждого кандидата отдельно вычислите правую часть исходного
                равенства. Отрицательный результат сразу исключает число. Затем
                проверьте подкоренное выражение и вычислите его неотрицательный
                корень. Только совпадение двух частей подтверждает решение.
                Не подставляйте кандидата лишь в квадратное уравнение: это
                повторяет уже выполненный шаг и не обнаруживает постороннего
                корня. В окончательной записи полезно кратко указать причину
                исключения, например отрицательность правой части. Так решение
                остаётся понятным при повторном чтении. Если исходное условие
                содержит несколько корней, знаковые ограничения и проверка
                понадобятся для каждого нового возведения в квадрат отдельно.
            """),
        ],
        "Решите уравнение √(x + 11) = x − 1.",
        [
            "Нужны x + 11 ≥ 0 и x − 1 ≥ 0; вместе получаем x ≥ 1.",
            "Возводим в квадрат: x + 11 = x² − 2x + 1, откуда "
            "x² − 3x − 10 = (x − 5)(x + 2) = 0. Кандидаты: 5 и −2.",
            "Число −2 нарушает ограничение знака. При x = 5 имеем "
            "√16 = 4 и 5 − 1 = 4. Единственный корень исходного уравнения равен 5.",
        ], 5,
        "После возведения в квадрат проверяйте неотрицательность правой части "
        "и исходное равенство.",
    ),
    "exponential-common-base": _lesson(
        [
            _section("Главная идея показательного уравнения", """
                В показательном уравнении неизвестная находится в показателе степени.
                Если обе части удаётся записать как степени одного положительного
                основания, не равного единице, задача часто сводится к обычному
                уравнению для показателей. Это не правило формального зачёркивания
                оснований. Оно опирается на свойство показательной функции принимать
                каждое своё значение только один раз. При основании больше
                единицы функция строго возрастает, а при положительном основании
                меньше единицы строго убывает. В обоих случаях равенство значений
                означает равенство показателей. Для основания, равного единице,
                это рассуждение не работает: все степени такого основания одинаковы.
            """, r"a^u=a^v\iff u=v,\quad a>0,\ a\ne1"),
            _section("Как увидеть общее основание", """
                Посмотрите, не является ли одно из чисел в условии целой
                степенью другого. Квадрат или куб небольшого числа часто
                позволяет сразу переписать правую часть в нужном виде.
                При возведении степени в степень показатели умножаются.
                Не путайте это действие с умножением двух степеней одинакового
                основания, где показатели складываются. Если в условии стоит
                обратное число, его можно представить отрицательной степенью
                положительного основания. Все такие преобразования нужно выполнять
                до приравнивания показателей. Одинаковый внешний вид чисел или
                близость их значений не заменяют точного равенства оснований;
                приближённые десятичные записи здесь особенно неуместны.
            """, r"(a^m)^n=a^{mn}"),
            _section("Линейное равенство после преобразования", """
                После приведения к общему основанию перепишите равенство показателей
                отдельной строкой. Обычно неизвестная входит туда линейно, поэтому
                остаётся перенести постоянное слагаемое и разделить на ненулевой
                коэффициент. Корень не обязан быть целым: дробный показатель
                допустим для положительного основания. Сохраните дробь точно
                и только затем переведите её в требуемую десятичную запись,
                если она конечна. В этом семействе коэффициент при неизвестной
                равен двум, поэтому возможные половинные значения возникают
                естественно. Не округляйте корень до ближайшего целого и
                не подменяйте решение подбором только целочисленных показателей.
            """),
            _section("Проверка без больших чисел", """
                Чтобы проверить ответ, не обязательно вычислять огромные значения
                степеней. Подставьте найденную неизвестную в показатель левой
                части и сравните его с преобразованным показателем правой
                части. Если показатели точно совпали и основание удовлетворяет
                необходимым условиям, исходное равенство выполнено. Такая проверка
                одновременно контролирует перенос знаков и деление при решении
                линейного уравнения. Единственность корня следует из однозначности
                показательной функции и ненулевого коэффициента при неизвестной
                в полученном равенстве. Если же обе части нельзя свести
                к общему основанию, этот конкретный способ не следует применять
                искусственно: потребуется другое преобразование, например подходящий логарифм.
            """),
        ],
        "Решите уравнение 3^(2x − 5) = 9^2.",
        [
            "Девять — квадрат трёх, поэтому 9² = (3²)² = 3⁴. Обе части имеют основание три.",
            "Поскольку основание больше единицы, приравниваем показатели: "
            "2x − 5 = 4. Получаем 2x = 9 и x = 4,5.",
            "Проверка: 2 · 4,5 − 5 = 4. Обе части исходного уравнения "
            "равны трём в четвёртой степени. Дробность корня не нарушает область определения.",
        ], Fraction(9, 2),
        "Сначала получите одинаковое допустимое основание, затем приравняйте показатели.",
    ),
    "logarithmic-product-domain": _lesson(
        [
            _section("Аргумент каждого логарифма положителен", """
                Логарифм действительного числа определён при положительном аргументе
                и положительном основании, отличном от единицы. В уравнении
                с несколькими логарифмами нужно проверить каждый исходный
                аргумент отдельно. Если аргументы являются суммой и разностью
                неизвестной с положительным числом, оба неравенства обычно
                сводятся к одному более строгому ограничению. Выпишите его
                до объединения логарифмов. Положительность произведения аргументов
                сама по себе недостаточна: произведение двух отрицательных
                чисел тоже положительно, но исходные логарифмы таких чисел
                не существуют. Именно потеря отдельных ограничений чаще
                всего приводит к лишнему отрицательному корню в этом семействе.
            """),
            _section("Сумма превращается в произведение", """
                Для одинакового допустимого основания сумма двух логарифмов
                положительных чисел равна логарифму их произведения. Это
                следствие умножения степеней с одним основанием: показатели
                складываются, когда сами степени умножаются. Поэтому внутри
                нового логарифма должно появиться произведение, а не сумма
                аргументов. Сохранив область допустимых значений, объедините
                левую часть. Затем используйте однозначность логарифмической
                функции: равные логарифмы с одним допустимым основанием
                имеют равные аргументы. Это утверждение верно и для
                основания меньше единицы. Направление монотонности важно
                для неравенств, но здесь решается равенство, поэтому дополнительного
                изменения знаков на этом шаге нет.
            """, r"\log_b u+\log_b v=\log_b(uv),\quad u,v>0"),
            _section("Два алгебраических кандидата", """
                Произведение суммы и разности удобно раскрыть по формуле
                разности квадратов. Получается квадрат неизвестной минус
                квадрат постоянного числа. После переноса постоянной части
                часто возникает уравнение, в котором квадрат неизвестной
                равен положительному числу. У такого уравнения два
                противоположных корня. Не теряйте отрицательный кандидат
                при алгебраическом решении, но и не включайте его
                автоматически в окончательный ответ. На отдельном шаге
                сравните оба числа с областью допустимых значений
                исходных логарифмов. В данном типе ограничение на
                положительность разности оставляет только положительный корень,
                расположенный правее соответствующей границы.
            """, r"(x-a)(x+a)=x^2-a^2"),
            _section("Подстановка и проверка равенства", """
                Для оставшегося корня сначала вычислите оба исходных аргумента
                и убедитесь, что они положительны. Затем можно проверить
                равенство либо через логарифмы небольших степеней, либо
                через произведение аргументов на уже установленной области
                определения. Проверка только преобразованного квадратного
                уравнения не обнаружит потерянную область определения,
                поэтому она недостаточна сама по себе. В ответе
                записывается найденный корень, а не значение каждого
                логарифма и не значение произведения аргументов.
                При повторении темы полезно различать две роли
                ограничений: они делают разрешённым правило объединения
                логарифмов и затем обеспечивают правильный отбор
                кандидатов, полученных при решении алгебраического уравнения.
            """),
        ],
        "Решите уравнение log_2(x − 6) + log_2(x + 6) = log_2(64).",
        [
            "Требуются x − 6 > 0 и x + 6 > 0, значит ОДЗ: x > 6.",
            "На ОДЗ объединяем логарифмы и приравниваем аргументы: "
            "(x − 6)(x + 6) = 64. Получаем x² = 100, кандидаты −10 и 10.",
            "Отрицательный кандидат не подходит. При x = 10 аргументы равны четырём "
            "и шестнадцати: log_2(4) + log_2(16) = 2 + 4 = 6 = log_2(64). Ответ: 10.",
        ], 10,
        "Сохраняйте положительность каждого исходного аргумента при объединении логарифмов.",
    ),
    "absolute-value-selected-root": _lesson(
        [
            _section("Модуль как расстояние", """
                Модуль разности двух чисел равен расстоянию между соответствующими
                точками числовой прямой. Поэтому уравнение с модулем разности
                можно читать геометрически: требуется найти точки на заданном
                расстоянии от фиксированного центра. Расстояние неотрицательно.
                При положительной правой части обычно существуют две точки,
                симметричные относительно центра: одна левее, другая правее.
                При нулевой правой части обе совпадают с центром,
                а при отрицательной решений нет. Эти случаи нужно
                различать до механического раскрытия модуля. Положительность
                самого модуля ничего не говорит о знаке неизвестной:
                левая точка вполне может иметь отрицательную координату.
            """, r"|x-a|=b,\quad b>0"),
            _section("Два линейных равенства", """
                Если модуль выражения равен положительному числу, само выражение
                может быть равно этому числу или противоположному ему.
                Поэтому исходное уравнение заменяют совокупностью двух
                линейных уравнений. Знак «или» существенен: неизвестная
                должна удовлетворять одному из равенств, а не двум
                одновременно. Решите каждое равенство отдельно и получите
                два кандидата. Для модуля линейного выражения на этом
                этапе обычно не требуется возведение в квадрат:
                оно создаёт более громоздкое квадратное уравнение без
                преимущества. Геометрическое понимание сразу показывает
                расположение корней и помогает избежать потери одной
                ветви при раскрытии модуля.
            """, r"|x-a|=b\iff x=a-b\ \text{или}\ x=a+b,\quad b\geq0"),
            _section("Как выбрать требуемый корень", """
                Формат краткого ответа часто требует не весь набор решений,
                а один корень с определённым свойством: меньший,
                больший, положительный или принадлежащий заданному интервалу.
                Отбор выполняется после нахождения всех кандидатов.
                Если спрашивается меньший корень при положительном
                расстоянии, он находится слева от центра, то есть
                получается вычитанием расстояния. Это сравнение не зависит
                от того, положителен или отрицателен центр. Слова
                «меньший» и «меньший по модулю» обозначают разные
                требования. Первое сравнивает положение на числовой
                прямой, второе — расстояния от нуля. Внимательное
                чтение вопроса предотвращает ошибку даже после безупречного решения уравнения.
            """),
            _section("Проверка симметрии и подстановкой", """
                Два найденных корня должны быть равноудалены от центра,
                а их среднее арифметическое должно совпасть с ним.
                Эти геометрические проверки помогают обнаружить ошибку
                знака при переносе слагаемого. Затем подставьте выбранное
                число в исходную разность и возьмите модуль результата.
                Он должен совпасть с заданным положительным расстоянием.
                Не заменяйте модуль скобками без учёта знака:
                для левого корня разность отрицательна, но её
                модуль положителен. В окончательном ответе запишите
                именно выбранное число, а в решении сохраните
                оба корня и причину выбора. Так видно, что
                вторая ветвь не была случайно забыта при раскрытии модуля.
            """),
        ],
        "Решите уравнение |x − 12| = 5. Укажите меньший корень.",
        [
            "Расстояние до числа двенадцать равно пяти. Получаем x − 12 = 5 "
            "или x − 12 = −5, откуда x = 17 или x = 7.",
            "Меньшее из двух чисел — семь; оно расположено слева от центра.",
            "Проверяем: |7 − 12| = |−5| = 5. Среднее корней равно "
            "(7 + 17)/2 = 12, что дополнительно подтверждает их симметрию.",
        ], 7,
        "Найдите обе точки на заданном расстоянии от центра и отберите корень по вопросу.",
    ),
    "power-product-quotient": _lesson(
        [
            _section("Степень с отрицательным показателем", """
                Отрицательный показатель степени обозначает обратное число к соответствующей
                положительной степени. Он не означает, что сама степень отрицательна.
                Например, положительное основание при отрицательном показателе даёт
                положительную дробь. Основание в таком выражении обязательно ненулевое,
                иначе пришлось бы делить на ноль. В этом семействе все основания
                положительные целые числа, поэтому операции определены. Перед вычислением
                полезно отделить знак показателя от знака основания: скобки вокруг
                отрицательного показателя показывают, к чему относится минус.
                Неправильное чтение этого знака меняет обратное число на противоположное
                и приводит к совершенно другому значению выражения.
            """, r"a^{-n}=\frac1{a^n},\quad a\ne0"),
            _section("Одинаковое основание позволяет объединять показатели", """
                При умножении степеней одного основания показатели складываются.
                При делении таких степеней показатель знаменателя вычитается
                из показателя числителя. Эти правила продолжают работать
                с нулевыми и отрицательными целыми показателями, если
                основание ненулевое. Поэтому вместо вычисления больших
                чисел можно выполнить короткое действие над показателями.
                Число без явно написанной степени считайте первой
                степенью этого же основания. Это особенно важно,
                когда в знаменателе стоит просто основание: его
                показатель равен единице, а не нулю. Само
                основание при объединении остаётся прежним; складывать
                основания или умножать их вместо показателей не требуется.
            """, r"\frac{a^m a^n}{a^k}=a^{m+n-k},\quad a\ne0"),
            _section("Порядок преобразования и работа со знаками", """
                Сначала перепишите выражение так, чтобы у всех множителей
                были явно видны основание и показатель. Затем запишите
                одной строкой действие над показателями, сохранив скобки
                вокруг отрицательных чисел. Только после вычисления
                итогового показателя находите значение оставшейся степени.
                Если выражение содержит степень степени, для неё
                действует другое правило: показатели перемножаются.
                Не смешивайте три операции — произведение степеней,
                частное степеней и степень степени. У каждой
                своё действие над показателями. Короткая промежуточная
                запись с числами помогает проверить, что минус
                отрицательного показателя не был потерян или ошибочно применён дважды.
            """),
            _section("Точность и проверка результата", """
                Прямое вычисление больших степеней создаёт лишнюю арифметику,
                а перевод отрицательных степеней в округлённые десятичные
                дроби может испортить точный ответ. Сохраняйте их
                как степени или обыкновенные дроби до сокращения.
                Для проверки небольшого примера можно отдельно
                заменить отрицательную степень обратной положительной
                и сократить числитель со знаменателем. Итог должен
                совпасть с результатом сложения показателей. Если
                суммарный показатель положителен, ответ при целом
                основании будет целым; при нулевом он равен
                единице; при отрицательном получится обратная степень.
                Все эти выводы предполагают, что исходное ненулевое
                основание действительно одно и то же во всех объединяемых множителях.
            """),
        ],
        "Вычислите (7^6 · 7^(-3))/7.",
        [
            "Все основания равны семи и ненулевые. Запишем знаменатель как 7¹.",
            "Показатели в произведении складываем, показатель знаменателя вычитаем: "
            "6 + (−3) − 1 = 2. Получаем 7² = 49.",
            "Проверка через дробь: 7⁶ · 7⁻³ / 7 = 7⁶ / (7³ · 7) = 7⁶/7⁴ = 49. "
            "Ни большие степени, ни приближённая десятичная запись "
            "обратного числа не понадобились.",
        ], 49,
        "При одинаковом ненулевом основании сначала выполните действия над показателями.",
    ),
    "radical-conjugates": _lesson(
        [
            _section("Как узнать сопряжённые выражения", """
                Сопряжёнными в этой задаче называются два выражения, которые
                содержат одинаковые слагаемые и различаются только знаком
                между ними. Их произведение удобно вычислять по формуле
                разности квадратов. Особенно полезен этот приём, когда
                одно слагаемое содержит квадратный корень из числа,
                которое не является полным квадратом. Такой корень
                может быть иррациональным, но произведение сопряжённых
                выражений оказывается рациональным. Значит, вычислять
                корень приближённо заранее не нужно. Сначала изучите
                структуру множителей: совпадают ли оба слагаемых
                и изменён ли только знак между ними. Лишь после
                этого выбирайте сокращённую формулу вместо полного раскрытия скобок.
            """, r"(u+v)(u-v)=u^2-v^2"),
            _section("Почему смешанные слагаемые исчезают", """
                Раскройте скобки обычным умножением: первый квадрат,
                два смешанных произведения с противоположными знаками
                и второй квадрат со знаком минус. Смешанные
                произведения одинаковы по модулю, поэтому взаимно
                уничтожаются. В результате остаётся только разность
                квадратов двух слагаемых. Если первое слагаемое
                является арифметическим квадратным корнем из
                неотрицательного числа, его квадрат равен самому
                подкоренному числу. Второе слагаемое возводится
                в квадрат обычным способом. Так иррациональная
                часть исчезает точно, а не вследствие приблизительного
                численного совпадения. Это объясняет, почему метод
                надёжнее округления каждого множителя перед их умножением.
            """, r"(\sqrt n+a)(\sqrt n-a)=n-a^2,\quad n\geq0"),
            _section("Условия и похожие неверные правила", """
                Для действительного квадратного корня подкоренное число
                должно быть неотрицательным. Важно также различать
                квадрат корня и корень из квадрата произвольного
                выражения. Квадрат арифметического корня возвращает
                исходное неотрицательное число, а корень из
                квадрата действительного числа возвращает его
                модуль. Кроме того, корень суммы обычно
                не равен сумме корней. Формула сопряжённых
                множителей не разрешает такие преобразования:
                она использует только разность квадратов
                и определение корня. Если знаки в
                двух скобках одинаковые, смешанные слагаемые
                не сократятся; потребуется формула квадрата суммы или разности,
                а не правило этого урока.
            """),
            _section("Контроль знака и перенос приёма", """
                Первый множитель с положительным корнем и положительным
                числом всегда положителен. Знак второго определяется
                тем, какое из этих чисел больше. Следовательно,
                знак произведения можно проверить сравнением подкоренного
                числа с квадратом второго слагаемого: квадратный
                корень монотонен на неотрицательной полуоси.
                Это позволяет заметить ошибку вычитания без
                вычисления самого корня. Та же идея
                сопряжения используется при освобождении знаменателя
                дроби от корня, но там дополнительно
                нужно проверить ненулевой знаменатель и
                умножить на сопряжённое выражение одновременно
                числитель и знаменатель. В данном семействе дроби нет,
                поэтому достаточно точного вычисления произведения двух скобок.
            """),
        ],
        "Вычислите (√37 + 4)(√37 − 4).",
        [
            "Подкоренное число положительно. Скобки сопряжённые, "
            "поэтому применяем разность квадратов.",
            "Получаем (√37)² − 4² = 37 − 16 = 21. Значение корня отдельно не вычисляем.",
            "Для проверки знака замечаем: 37 > 16, значит √37 > 4. Оба множителя "
            "положительны, и положительный ответ согласуется с условием. Иррациональные "
            "смешанные слагаемые при раскрытии скобок сокращаются точно.",
        ], 21,
        "В произведении сопряжённых скобок используйте разность квадратов до вычисления корней.",
    ),
    "rational-removable-factor": _lesson(
        [
            _section("Сначала допустимость подстановки", """
                Рациональное выражение может быть не определено при
                некоторых значениях переменной. Если в задании
                требуется вычислить дробь при конкретном значении,
                сначала проверьте знаменатель. Нулевой знаменатель
                делает исходное выражение недопустимым, даже если
                числитель тоже обращается в ноль. В этом
                случае нельзя объявить результат нулём или
                воспользоваться сокращённой формулой как будто
                ограничения исчезли. Сокращение сохраняет значения
                только на исходной области определения.
                В корректно поставленных задачах этого семейства
                указанное значение отличается от запрещённого, поэтому
                подстановка разрешена. Явная проверка этого факта занимает
                одну строку и делает дальнейшее преобразование обоснованным.
            """),
            _section("Разложение числителя на множители", """
                Разность квадрата переменной и квадрата постоянного
                числа раскладывается в произведение разности
                и суммы этих двух величин. Если
                знаменатель совпадает с одним из множителей,
                появляется возможность сокращения. Именно множитель,
                а не отдельное слагаемое, должен быть
                общим для всего числителя и всего
                знаменателя. Нельзя зачёркивать одинаковые буквы
                или числа внутри суммы произвольно.
                Поэтому первым действием запишите факторизацию
                полностью, с обеими скобками. После
                этого видно, какая ненулевая величина
                делит числитель и знаменатель одновременно.
                Оставшаяся скобка задаёт более простое выражение на той же допустимой области.
            """, r"\frac{x^2-a^2}{x-a}=x+a,\quad x\ne a"),
            _section("Почему упрощение облегчает вычисление", """
                Прямая подстановка в исходную дробь требует
                возведения числа в квадрат, вычитания
                и последующего деления. После сокращения
                часто остаётся только сложение двух
                чисел. Это уменьшает количество действий
                и вероятность арифметической ошибки, особенно
                при больших значениях. Однако короткая
                формула не является новой областью
                определения исходного выражения. Даже если
                она допускает запрещённую ранее точку,
                результат в этой точке не отвечает
                исходному вопросу. Полезно хранить запись
                ограничения рядом с каждым сокращённым выражением.
                Тогда при дальнейших преобразованиях или решении уравнений не будет
                незаметно добавлено лишнее допустимое значение переменной.
            """),
            _section("Два независимых способа проверки", """
                После нахождения ответа подставьте заданное значение
                в исходный числитель и знаменатель
                отдельно. Их точное частное должно
                совпасть со значением сокращённой формулы.
                Такая проверка полезна тем, что
                использует другой порядок арифметических
                действий. Ещё один способ —
                умножить найденный ответ на исходный
                ненулевой знаменатель и сравнить
                с числителем. В обоих случаях
                сохраняйте точность: округление до
                деления может скрыть ошибку.
                Если при проверке обнаружен ноль в знаменателе,
                остановитесь и пересмотрите условие или переписанные данные, вместо
                попытки присвоить дроби значение по результату сокращения.
            """),
        ],
        "Найдите значение (x² − 49)/(x − 7) при x = 11.",
        [
            "Проверяем область: 11 − 7 = 4 ≠ 0, подстановка в исходную дробь допустима.",
            "Разложим числитель: x² − 49 = (x − 7)(x + 7). "
            "При x ≠ 7 после сокращения остаётся x + 7, поэтому ответ равен 11 + 7 = 18.",
            "Независимая арифметическая проверка: (121 − 49)/(11 − 7) = 72/4 = 18. "
            "Ограничение относится к исходной дроби и сохраняется после сокращения.",
        ], 18,
        "Сокращайте общий ненулевой множитель, сохраняя исходную область определения.",
    ),
    "logarithm-difference": _lesson(
        [
            _section("Разность может быть проще каждого слагаемого", """
                Отдельные логарифмы в выражении не обязаны
                иметь удобные числовые значения. Однако
                их разность при одинаковом основании
                может вычисляться точно после объединения.
                Логарифм отвечает на вопрос о
                показателе степени: в какую степень
                нужно возвести основание, чтобы получить
                аргумент. При делении степеней одного
                основания показатели вычитаются. Поэтому
                вычитание логарифмов соответствует делению
                аргументов, а не их вычитанию.
                Понимание связи со степенями помогает восстановить
                правило даже без механического запоминания и сразу
                показывает, какое действие нужно выполнить внутри нового логарифма.
            """, r"\log_b u-\log_b v=\log_b\frac uv"),
            _section("Условия применения правила", """
                Основание обоих логарифмов должно быть одним
                и тем же положительным числом,
                не равным единице. Оба исходных
                аргумента должны быть положительными.
                Недостаточно проверить только положительность
                их частного: частное двух
                отрицательных чисел тоже положительно,
                а исходные логарифмы не существуют
                в действительных числах. В числовых
                задачах эти ограничения обычно
                видны непосредственно из записи,
                но их всё равно стоит
                отметить перед преобразованием. Если основания различны,
                простое правило разности применять нельзя. Иногда сначала помогает
                переход к общему основанию, однако это уже дополнительное действие,
                которое должно быть явно обосновано.
            """, r"b>0,\quad b\ne1,\quad u>0,\quad v>0"),
            _section("Как найти точное значение", """
                После объединения вычислите частное аргументов
                точно. Затем представьте полученное
                число как степень основания.
                Если это удалось, логарифм
                равен соответствующему показателю.
                Проверка состоит в обратном
                действии: возведите основание
                в найденную степень и
                убедитесь, что получился именно
                аргумент нового логарифма.
                Не требуется отдельно вычислять
                два исходных логарифма или
                пользоваться приближёнными таблицами. Такая предварительная оценка
                добавляет погрешность и часто скрывает простую целую степень,
                заложенную в условии. Особенно внимательно считайте количество
                множителей основания: значение логарифма — показатель, а не результат
                возведения основания в эту степень.
            """),
            _section("Знак и сравнение величин", """
                При основании больше единицы логарифм
                числа больше единицы положителен,
                логарифм единицы равен нулю,
                а логарифм положительной дроби
                меньше единицы отрицателен.
                Поэтому знак результата можно
                проверить сравнением исходных
                аргументов: если первый больше
                второго, их частное больше
                единицы и разность положительна.
                При положительном основании меньше единицы направление
                меняется, поскольку логарифмическая функция убывает.
                Эта проверка не заменяет вычисление, но помогает
                заметить перестановку числителя и знаменателя. В окончательном
                ответе запишите показатель степени; само частное аргументов
                остаётся лишь промежуточным числом, даже если его удалось
                вычислить намного раньше остальных действий.
            """),
        ],
        "Вычислите log_3(405) − log_3(5).",
        [
            "Основания одинаковы и больше единицы, оба аргумента положительны. "
            "Поэтому разность равна log_3(405/5).",
            "Частное равно восьмидесяти одному: 405/5 = 81 = 3⁴. Следовательно, логарифм равен 4.",
            "Для проверки возводим три в четвёртую степень и получаем восемьдесят один. "
            "Разность положительна, поскольку первый исходный аргумент больше второго. "
            "Ответом является показатель четыре, а не число восемьдесят один.",
        ], 4,
        "Объедините разность в логарифм частного и распознайте точную степень основания.",
    ),
    "trigonometric-double-angle": _lesson(
        [
            _section("Двойной угол через исходный угол", """
                Формула синуса двойного угла выражает
                искомую величину через синус
                и косинус исходного угла.
                Поэтому одного заданного синуса
                сначала недостаточно: нужно
                восстановить косинус и
                правильно выбрать его знак.
                Искать сам угол в
                градусах или радианах
                при этом не требуется.
                Это важное преимущество алгебраического преобразования:
                угол может не совпадать с известным табличным
                значением, но искомое выражение всё равно вычисляется
                точно. Условие о четверти не является лишней
                информацией: именно оно позволяет однозначно восстановить
                знак косинуса и, следовательно, знак окончательного ответа.
            """, r"\sin(2\alpha)=2\sin\alpha\cos\alpha"),
            _section("Восстановление косинуса и выбор знака", """
                Основное тригонометрическое тождество связывает
                квадраты синуса и косинуса.
                Выразите квадрат косинуса
                как единицу минус
                квадрат известного синуса.
                Полученное неотрицательное число
                определяет модуль косинуса,
                но ещё не его знак.
                Во второй четверти синус
                положителен, а косинус
                отрицателен, поэтому перед
                арифметическим корнем ставится минус.
                Если забыть этот шаг, числовой модуль ответа
                может оказаться верным, а знак — противоположным.
                Проверяйте также допустимость заданного синуса: его
                модуль не должен превышать единицу, а строгие границы
                четверти исключают значения, соответствующие её граничным осям.
            """, r"\cos\alpha=-\sqrt{1-\sin^2\alpha},\quad\frac\pi2<\alpha<\pi"),
            _section("Работа с точными дробями", """
                Если синус задан обыкновенной дробью,
                возводите в квадрат числитель
                и знаменатель отдельно.
                Единицу приведите к
                тому же знаменателю,
                затем выполните вычитание.
                В специально подобранных
                задачах числитель полученной
                дроби является полным
                квадратом, поэтому корень
                извлекается точно. Подставьте
                оба отношения в формулу двойного угла
                и сократите общий знаменатель с коэффициентом
                перед выражением, если это возможно. Даже если
                промежуточная дробь имеет бесконечную десятичную запись,
                окончательный результат после сокращения может быть целым.
                Ранний перевод в приближённые десятичные значения уничтожает
                эту точность и здесь совершенно не нужен.
            """),
            _section("Две проверки результата", """
                Первую проверку выполните через основное
                тождество: квадраты найденных
                синуса и косинуса
                должны в сумме
                дать единицу. Вторая
                проверка использует диапазон
                двойного угла. Если
                исходный угол строго
                между половиной числа
                пи и числом пи,
                двойной угол находится между пи и
                удвоенным пи. На этом промежутке синус
                отрицателен, что согласуется с произведением
                положительного синуса и отрицательного косинуса.
                Кроме знака контролируйте масштаб: модуль синуса
                двойного угла не больше единицы. После умножения
                на положительный коэффициент модуль ответа не может
                превышать этот коэффициент, даже если вычисления содержат
                большие промежуточные числа.
            """),
        ],
        "Найдите 169·sin(2α), если sin α = 5/13 и π/2 < α < π.",
        [
            "Квадрат косинуса равен 1 − 25/169 = 144/169. Угол во второй четверти, "
            "поэтому cos α = −12/13.",
            "Подставляем в формулу: 169 · 2 · (5/13) · (−12/13) = −120. "
            "Знаменатель сто шестьдесят девять полностью сокращается с коэффициентом.",
            "Проверка: 25/169 + 144/169 = 1. Ответ отрицателен, как синус угла "
            "между пи и удвоенным пи, а его модуль меньше заданного коэффициента.",
        ], -120,
        "Знак косинуса выбирается по четверти; точные дроби сокращайте до перевода в десятичные.",
    ),
    "piecewise-function-value": _lesson(
        [
            _section("Что требуется прочитать с графика", """
                Запись значения функции при заданном аргументе
                означает поиск ординаты точки графика,
                имеющей указанную абсциссу. Сначала найдите
                аргумент на горизонтальной оси,
                затем соответствующую точку графика
                и её координату по вертикали.
                Это отличается от обратного
                вопроса, когда задано значение
                функции и требуется найти
                аргументы. Также значение функции
                не является её производной:
                здесь читается высота графика, а не его наклон.
                В данном семействе график состоит из прямых
                отрезков с точно заданными вершинами. Поэтому промежуточные
                значения можно восстановить вычислением, не оценивая их
                на глаз по положению линии между клетками рисунка.
            """),
            _section("Выбор нужного прямолинейного участка", """
                Сравните заданный аргумент с абсциссами
                соседних вершин ломаной.
                Найдите тот отрезок,
                проекция которого содержит
                искомое число. Все
                дальнейшие вычисления относятся
                только к этому
                участку. Нельзя соединять
                самую левую и
                самую правую вершины
                одной воображаемой прямой,
                если между ними есть излом: наклон
                на разных участках может отличаться.
                Если аргумент совпадает с абсциссой вершины,
                значение уже задано её ординатой. Если
                аргумент лежит строго внутри отрезка, используйте
                пропорциональность приращений координат. При отсутствии продолжения
                графика за крайними точками нельзя произвольно экстраполировать его наружу.
            """),
            _section("Линейная интерполяция", """
                На прямом отрезке равным приращениям
                аргумента соответствуют равные
                приращения значения функции.
                Определите, какую долю
                горизонтального пути от
                левой вершины до
                правой составляет путь
                до нужного аргумента.
                Возьмите такую же
                долю вертикального изменения
                и прибавьте к левой ординате.
                Если аргумент находится ровно посередине,
                его ордината равна среднему арифметическому
                ординат концов. Это правило верно
                для прямого отрезка, но не для
                произвольной кривой между теми же точками.
                Формула работает и при убывающем участке: вертикальное
                изменение тогда отрицательно и автоматически уменьшает исходную ординату.
            """, r"f(t)=y_A+\frac{t-x_A}{x_B-x_A}(y_B-y_A),\quad x_A\leq t\leq x_B"),
            _section("Проверка масштаба и смысла", """
                Для внутренней точки отрезка вычисленная
                ордината должна лежать
                между ординатами его
                концов. Если она
                вышла за этот
                диапазон, вероятно,
                неверно определена доля
                пути или выбран
                другой участок.
                Проверьте также направление:
                на возрастающем отрезке
                большему аргументу соответствует большее значение.
                При чтении рисунка ориентируйтесь на подписи
                координат, а не на видимый угол
                наклона: масштабы горизонтальной и вертикальной осей
                могут различаться. Точное текстовое описание вершин
                позволяет выполнить те же рассуждения без рисунка.
                В ответе укажите ординату, а не координаты всей точки
                и не длину пройденного участка ломаной.
            """),
        ],
        "График f — ломаная с вершинами A(2; 1), B(8; 7), C(12; 3). Найдите f(5).",
        [
            "Аргумент пять лежит между абсциссами двух первых вершин, поэтому нужен отрезок AB.",
            "Пять — середина между двумя и восемью. На прямом отрезке ордината "
            "середины равна (1 + 7)/2 = 4, следовательно, f(5) = 4.",
            "Проверяем по приращениям: горизонтальный путь равен половине полного, "
            "вертикальный подъём тоже составляет половину от шести, то есть три. "
            "Начальная ордината один плюс три даёт четыре.",
        ], 4,
        "Сначала выберите участок графика, затем восстановите ординату "
        "по доле горизонтального пути.",
    ),
    "derivative-positive-length": _lesson(
        [
            _section("Изображена производная, а спрашивают о функции", """
                В задачах по графику производной важно
                сначала назвать изображённый объект.
                Ордината такого графика показывает
                значение производной, а
                не значение самой
                функции. Если производная
                положительна на интервале,
                функция возрастает; если
                отрицательна — убывает.
                Поэтому для поиска
                возрастания нужны части графика
                производной над осью абсцисс. Направление
                движения самой линии производной вверх
                или вниз отвечает другому вопросу.
                Например, производная может увеличиваться, оставаясь
                отрицательной: исходная функция в этот момент
                всё ещё убывает. Такое различение знака и
                изменения значения является центральной идеей этого типа задач.
            """, r"f'(x)>0\ \Longrightarrow\ f\text{ возрастает на интервале}"),
            _section("Нули разделяют знаковые промежутки", """
                Найдите пересечения графика производной
                с горизонтальной осью.
                Их абсциссы разбивают
                рассматриваемый интервал на
                части, внутри которых
                знак производной виден
                непосредственно. Для прямого
                отрезка с противоположными
                значениями на концах
                нуль находится между
                концами и вычисляется линейной
                интерполяцией. Если модули ординат
                одинаковы, нулевое значение достигается
                в середине по горизонтали. Не принимайте
                за нули точки излома, если их
                ординаты отличны от нуля. Вершина ломаной
                может лежать выше или ниже оси и
                тогда сама по себе не меняет знак производной.
            """),
            _section("От промежутков к суммарной длине", """
                После определения знаков выпишите
                все промежутки положительности
                производной в заданной
                области. Для каждого
                найдите длину как
                правую границу минус
                левую. Затем сложите
                эти длины. Здесь
                не требуется ни
                площадь под графиком,
                ни количество видимых участков,
                ни длина наклонных отрезков линии.
                Измеряется суммарная длина промежутков по
                оси аргумента. Включение или исключение
                отдельной конечной точки не меняет эту
                величину. Если график задан на более
                широком участке, сначала ограничьте найденные интервалы
                областью из вопроса. Часть положительного участка за
                пределами указанной области не должна увеличивать ответ.
            """),
            _section("Как проверить выбранные интервалы", """
                Возьмите по одной внутренней
                точке каждого выбранного
                промежутка и убедитесь,
                что соответствующая ордината
                производной положительна.
                На пропущенных промежутках
                она должна быть
                отрицательна или условия
                требуют отдельного анализа
                нулевого участка. Для
                ломаной без горизонтальных нулевых
                отрезков проверка особенно проста.
                Общая длина возрастания не может
                превышать длину всей рассматриваемой области.
                Можно также сложить длины убывания
                и возрастания: при наличии только отдельных
                нулей получится полная длина. Эта проверка
                помогает заметить потерянный крайний участок, который
                начинается или заканчивается на границе рисунка, а не в очередном нуле.
            """),
        ],
        "График f′ — ломаная A(0; -3), B(4; 3), C(8; -3), D(12; 3). "
        "Найдите суммарную длину промежутков возрастания f на (0; 12).",
        [
            "Ординаты концов каждого отрезка противоположны и равны по модулю. "
            "Нули производной находятся посередине: при x = 2, 6 и 10.",
            "График производной выше оси на (2; 6) и (10; 12). Именно там функция возрастает.",
            "Суммарная длина равна (6 − 2) + (12 − 10) = 6. "
            "Оставшиеся промежутки убывания тоже имеют общую длину шесть; "
            "вместе они дают двенадцать.",
        ], 6,
        "Для возрастания f выбирайте положительные значения f′ и складывайте длины по оси x.",
    ),
    "tangent-from-two-points": _lesson(
        [
            _section("Производная как наклон касательной", """
                Геометрический смысл производной связывает её
                с угловым коэффициентом касательной
                к графику в рассматриваемой
                точке. Этот коэффициент показывает,
                насколько меняется ордината
                прямой при единичном
                увеличении абсциссы.
                Он не равен
                ординате точки касания
                и не является
                самим углом наклона. Угловой
                коэффициент равен тангенсу этого угла,
                когда угол и координатные масштабы
                определены обычным способом. Для краткого
                числового ответа обычно достаточно двух точных
                точек касательной. Восстанавливать всю функцию
                или вычислять угол по рисунку не требуется,
                поскольку наклон прямой однозначно определяется отношением приращений координат.
            """, r"f'(x_0)=k_{\text{касательной}}"),
            _section("Какие точки можно использовать", """
                Выбранные точки должны лежать именно
                на касательной. Две произвольные
                точки исходного криволинейного
                графика задают секущую,
                наклон которой обычно
                отличается от производной
                в точке касания.
                При чтении рисунка
                найдите подпись прямой
                и отметки принадлежности
                точек. Сама точка касания
                может быть одной из двух
                используемых точек, но это не
                обязательно. Любая пара разных точек
                одной невертикальной прямой имеет одинаковое
                отношение вертикального приращения к горизонтальному.
                Поэтому удобно выбирать точки с известными
                точными координатами, а не оценивать неназванные пересечения
                касательной с линиями сетки на глаз.
            """),
            _section("Вычисление отношения приращений", """
                Вычтите ординату первой точки из
                ординаты второй, а
                затем разделите на
                разность абсцисс в
                том же порядке.
                Порядок можно поменять
                одновременно в числителе
                и знаменателе: оба
                знака изменятся, но
                частное сохранится.
                Если поменять порядок только
                в одной разности, знак наклона
                будет ошибочным. Знаменатель должен
                быть ненулевым. В задачах на
                конечную производную касательная не является
                вертикальной, поэтому две её разные
                точки имеют разные абсциссы. После нахождения
                наклона перенесите его значение в ответ для
                производной именно в указанной точке касания, а не во всех точках функции.
            """, r"k=\frac{y_B-y_A}{x_B-x_A},\quad x_A\ne x_B"),
            _section("Проверки знака и масштаба", """
                Если прямая поднимается при движении
                вправо, её наклон
                положителен; если опускается,
                отрицателен. Горизонтальная
                касательная имеет нулевой
                наклон. Эти наблюдения
                помогают проверить знак,
                но величину нельзя
                надёжно измерять видимым
                углом на экране:
                масштабы осей могут различаться.
                Используйте подписанные координаты. Дополнительно
                умножьте найденный коэффициент на разность
                абсцисс: должно получиться исходное изменение
                ординат. Если в ответе оказалась
                просто разность высот, вероятно, забыто
                деление на горизонтальное приращение. Если получилось
                обратное отношение, проверьте порядок осей: производная
                показывает изменение значения функции относительно изменения аргумента,
                а не наоборот.
            """),
        ],
        "Касательная к графику f при x = 0 проходит через A(-2; 7) и B(2; 1). Найдите f′(0).",
        [
            "По условию обе точки принадлежат касательной. При движении от A к B "
            "приращение ординаты равно 1 − 7 = −6, приращение абсциссы равно 2 − (−2) = 4.",
            "Угловой коэффициент касательной равен −6/4 = −1,5. Поэтому f′(0) = −1,5.",
            "Знак согласуется с рисунком: прямая опускается вправо. "
            "Проверка приращения: −1,5 · 4 = −6, что совпадает с разностью заданных ординат.",
        ], Fraction(-3, 2),
        "Производная в точке касания равна отношению приращений y и x на касательной.",
    ),
    "derivative-turning-point": _lesson(
        [
            _section("Минимум определяется сменой поведения функции", """
                В точке локального минимума значения
                функции поблизости не меньше,
                чем в самой точке.
                Удобный достаточный признак
                состоит в переходе
                от убывания к
                возрастанию. Для дифференцируемой
                функции это можно
                распознать по знаку
                производной: слева она
                отрицательна, а справа положительна.
                Поэтому график производной даёт информацию
                об экстремумах исходной функции, даже
                если её собственные ординаты неизвестны.
                Не путайте минимум функции с самой
                нижней точкой графика производной: это
                разные объекты. Нужна абсцисса перехода знака
                через ноль, а не место, где изображённая
                производная принимает наименьшее видимое значение.
            """, r"f':\ -\ \to\ +\quad\Longrightarrow\quad\text{локальный минимум }f"),
            _section("Почему одного нуля недостаточно", """
                Нулевое значение производной является кандидатом
                для экстремума, но
                само по себе
                не гарантирует его.
                Производная может коснуться
                оси и сохранить
                один знак по
                обе стороны. Тогда
                функция продолжит возрастать
                или убывать через
                эту точку без экстремума.
                Поэтому после нахождения нуля обязательно
                исследуйте соседние знаки. Переход с
                плюса на минус указывает на
                максимум, а с минуса на
                плюс — на минимум. В данном
                семействе производная изображена возрастающим прямым
                отрезком с отрицательной левой и положительной
                правой ординатой. Эти данные обеспечивают ровно один нуль и нужную смену знака.
            """),
            _section("Как найти абсциссу пересечения точно", """
                Для прямого отрезка производной сначала
                вычислите наклон как
                отношение изменения ординаты
                к изменению абсциссы.
                Затем определите, сколько
                нужно пройти по
                горизонтали от левой
                точки, чтобы отрицательная
                ордината поднялась до
                нуля. Требуемое увеличение
                ординаты делится на положительный
                наклон. Прибавьте найденный горизонтальный
                путь к левой абсциссе. Получится
                точная координата пересечения. Такой способ
                удобнее оценки рисунка по клеткам
                и работает даже тогда, когда
                нуль не находится посередине отрезка.
                Равенство расстояний до концов возникает только
                при противоположных ординатах равного модуля, а не при любой смене знака.
            """),
            _section("Какой именно ответ требуется", """
                По графику производной можно определить
                абсциссу экстремума и
                тип экстремума, но
                обычно нельзя восстановить
                само минимальное значение
                функции без дополнительного
                условия. Все функции,
                различающиеся постоянным вертикальным
                сдвигом, имеют одинаковую
                производную и одинаковые
                абсциссы экстремумов. Поэтому внимательно
                различайте слова «точка минимума»
                и «значение минимума» в вопросе.
                В этом семействе явно запрашивается
                абсцисса. Проверьте, что она лежит
                внутри указанного интервала, а не
                совпадает с его внешней границей.
                После вычисления ещё раз назовите знаки
                производной слева и справа: это завершает доказательство минимума,
                а не только нахождение нуля.
            """),
        ],
        "График f′ на (1; 7) — отрезок от A(1; -4) до B(7; 8). "
        "Найдите абсциссу точки минимума f.",
        [
            "Наклон прямой производной равен (8 − (−4))/(7 − 1) = 12/6 = 2.",
            "Чтобы подняться от ординаты −4 до нуля, нужно увеличить x на 4/2 = 2. "
            "Абсцисса нуля равна 1 + 2 = 3.",
            "Слева от трёх производная отрицательна, справа положительна. "
            "Значит, функция сначала убывает, затем возрастает и имеет минимум при x = 3. "
            "Само значение функции в этой точке из данных не определяется.",
        ], 3,
        "Для минимума нужен переход f′ с минуса на плюс; ответом служит абсцисса перехода.",
    ),
    "antiderivative-initial-value": _lesson(
        [
            _section("Первообразная обращает действие производной", """
                Первообразной заданной функции на интервале
                называется функция, производная
                которой равна заданной
                в каждой точке
                этого интервала. Поэтому
                задача о первообразной
                требует восстановить исходную
                зависимость по известной
                скорости её изменения.
                Для линейной функции
                первообразная является квадратным многочленом
                с возможной постоянной добавкой.
                Проверка всегда выполняется дифференцированием:
                производная найденного выражения должна
                совпасть с данным выражением точно.
                Важно не перепутать направления действий.
                Если вместо первообразной ещё раз
                продифференцировать заданную линейную функцию, получится постоянная,
                которая отвечает совсем другой задаче и не удовлетворяет определению первообразной.
            """, r"F'(x)=f(x)"),
            _section("Откуда берётся произвольная постоянная", """
                Производная постоянного числа равна нулю.
                Поэтому прибавление любой
                постоянной к одной
                первообразной даёт другую
                первообразную той же
                функции. На общем
                интервале все первообразные
                различаются именно постоянной.
                Из одной производной
                нельзя узнать вертикальное
                положение графика исходной функции.
                Его фиксирует дополнительное условие,
                например известное значение в одной
                точке. Не выбирайте постоянную равной
                нулю автоматически: это лишь один
                частный представитель семейства. В задачах
                с начальным условием именно найденная
                постоянная обеспечивает правильное значение искомой первообразной,
                а её пропуск изменяет ответ на всех аргументах одновременно.
            """, r"\int (ax+b)\,dx=\frac a2x^2+bx+C"),
            _section("Использование начального условия", """
                Сначала запишите общий вид первообразной,
                сохранив неизвестную постоянную.
                Затем подставьте аргумент
                и значение из
                начального условия. Получится
                линейное равенство для
                постоянной, которое нужно
                решить до вычисления
                значения в другой
                точке. Если начальная
                точка имеет нулевую абсциссу,
                переменные слагаемые исчезают и
                постоянная сразу равна данному значению.
                При ненулевой начальной точке придётся
                предварительно вычесть значения остальных слагаемых.
                После нахождения постоянной вернитесь к
                полной формуле первообразной и подставьте
                требуемый аргумент. Не используйте начальное значение
                вместо всей функции: оно относится только к одной указанной точке.
                Область рассматриваемого многочлена — вся числовая прямая,
                поэтому обе подстановки допустимы.
            """),
            _section("Проверка двух независимых условий", """
                Правильное решение должно одновременно удовлетворять
                условию на производную
                и известному значению
                первообразной. Проверьте их
                отдельно. При дифференцировании
                квадратного слагаемого возникает
                множитель два, который
                сокращает половину коэффициента
                исходной линейной функции.
                Производная линейного слагаемого
                возвращает свободный член заданной
                функции, а постоянная исчезает.
                После этого проверьте подстановкой
                начальную точку. Если первая проверка
                проходит, а вторая нет, ошибка
                скорее всего в постоянной. Если
                не проходит первая, нужно пересмотреть
                коэффициенты первообразной. Только после обеих проверок
                окончательное числовое значение можно считать согласованным
                с полным условием задачи.
            """),
        ],
        "F — первообразная f(x) = 4x + 3. Известно F(0) = 5. Найдите F(2).",
        [
            "Общий вид первообразной: F(x) = 2x² + 3x + C, поскольку производная этого "
            "выражения равна 4x + 3 при любой постоянной.",
            "Подставляем ноль: F(0) = C = 5. Следовательно, F(x) = 2x² + 3x + 5.",
            "Искомое значение F(2) = 2 · 4 + 3 · 2 + 5 = 19. "
            "Производная проверена, начальное условие выполнено; постоянная не была потеряна.",
        ], 19,
        "Запишите первообразную с постоянной, найдите её из начального условия "
        "и проверьте производную.",
    ),
    "integral-signed-areas": _lesson(
        [
            _section("Интеграл учитывает знак функции", """
                Определённый интеграл по возрастающим границам
                можно понимать как
                накопление знаковой площади.
                Участок графика над
                осью абсцисс вносит
                положительный вклад, а
                участок под осью
                — отрицательный.
                Поэтому интеграл не
                всегда равен обычной
                геометрической площади всей фигуры.
                Если функция меняет знак,
                площади разных участков вычитаются,
                а не просто складываются.
                Итог может быть положительным,
                отрицательным или нулевым, хотя
                каждая отдельная геометрическая площадь
                неотрицательна. Такое понимание особенно удобно
                для графика из прямых отрезков: вклад каждого
                участка вычисляется через знакомые площади треугольников или трапеций
                без поиска сложной первообразной.
            """),
            _section("Разбиение по нулям и вершинам", """
                Начните с границ интегрирования и
                отметьте, где внутри
                них график пересекает
                горизонтальную ось.
                Эти точки разделяют
                положительные и отрицательные
                вклады. Затем используйте
                вершины ломаной, чтобы
                разбить полученные фигуры
                на простые части.
                Если один наклонный отрезок
                пересекает ось между заданными
                вершинами, сначала найдите абсциссу
                пересечения по линейной зависимости.
                Нельзя считать всю площадь под
                таким отрезком положительной или отрицательной
                только по знаку одного конца.
                В рассматриваемом семействе точки перехода через
                ось заданы явно, поэтому после чтения координат
                можно сразу вычислять основания и высоты соответствующих треугольников.
            """),
            _section("Геометрическое вычисление вкладов", """
                Основание треугольника на оси аргумента
                равно разности абсцисс
                его крайних точек.
                Высота равна расстоянию
                вершины до оси,
                то есть модулю
                её ординаты.
                Площадь находится как
                половина произведения основания
                на высоту.
                Только после вычисления положительной
                геометрической площади назначьте знак
                вклада по расположению фигуры.
                Такой порядок уменьшает риск двойного
                минуса: отрицательную ординату не нужно
                одновременно использовать как отрицательную высоту
                и ещё раз вычитать полученную площадь.
                Для трапеции можно взять среднее двух
                одноимённых высот и умножить на основание, либо
                разложить её на прямоугольник и треугольник с сохранением того же знака.
            """, r"\int_a^b f(x)\,dx=S_{\text{над осью}}-S_{\text{под осью}}\quad(a<b)"),
            _section("Что проверять в конце", """
                Сравните размеры положительной и отрицательной
                частей: знак ответа
                должен соответствовать преобладающей
                площади. Если требуется
                именно интеграл, не
                заменяйте отрицательный результат
                его модулем.
                При перестановке границ
                интегрирования знак всего
                результата меняется.
                Проверяйте также, что все
                учтённые участки лежат внутри
                заданных границ: продолжение графика
                снаружи не участвует в ответе.
                Интеграл аддитивен по соседним интервалам,
                поэтому вычисление суммы нескольких малых
                вкладов должно совпасть с вычислением
                более крупных объединённых фигур одного знака.
                Единицы результата являются произведением единиц ординаты
                и аргумента, а не просто длиной по одной из координатных осей.
            """),
        ],
        "График f — ломаная A(0; -2), B(4; 0), C(8; 3), D(12; 0). "
        "Найдите интеграл от 0 до 12 функции f.",
        [
            "На отрезке от нуля до четырёх график ниже оси. Площадь треугольника "
            "равна 4 · 2 / 2 = 4, его вклад в интеграл равен −4.",
            "На отрезке от четырёх до двенадцати график выше оси и образует "
            "треугольник площади (12 − 4) · 3 / 2 = 12.",
            "Суммарный интеграл равен −4 + 12 = 8. Геометрическая площадь обеих "
            "частей равнялась бы шестнадцати, но это другая величина, "
            "поскольку она не учитывает знак.",
        ], 8,
        "Для интеграла вычитайте площадь под осью из площади над осью "
        "и учитывайте направление границ.",
    ),
}


def build_lessons(profile: ProfileSource) -> list[dict]:
    """Return fresh authored lessons and links to the centrally built static practice."""
    slots = {slot.number: {skill.id for skill in slot.skills} for slot in profile.slots}
    lessons = []
    for family_id, material in _LESSONS.items():
        family = _CATALOG[family_id]
        if not set(family.skill_ids) <= slots.get(family.slot, set()):
            raise ValueError("Lesson requires the corresponding profile skills")
        lessons.append({
            "id": f"course-{family.id}", "title": family.title, "slot": family.slot,
            "minutes": 5, "skill_ids": list(family.skill_ids),
            **deepcopy(material),
            "family_ids": [family.id],
            "practice_task_ids": [f"course-{family.id}-{seed}" for seed in range(3)],
        })
    return lessons
